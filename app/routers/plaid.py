from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products

from app.config import get_settings
from app.database import get_db
from app.models import PlaidItem, Account, Institution, Transaction
from app.schemas import PlaidLinkTokenResponse, PlaidExchangeRequest

router = APIRouter(prefix="/api/plaid", tags=["plaid"])

PLAID_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def get_plaid_client():
    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise HTTPException(
            status_code=503,
            detail="Plaid credentials not configured. Set PLAID_CLIENT_ID and PLAID_SECRET in .env",
        )

    configuration = plaid.Configuration(
        host=PLAID_ENV_MAP.get(settings.plaid_env, plaid.Environment.Sandbox),
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


@router.post("/link-token", response_model=PlaidLinkTokenResponse)
def create_link_token():
    client = get_plaid_client()

    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Budget Buddy",
        country_codes=[CountryCode("CA"), CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id="budget-buddy-user"),
    )

    response = client.link_token_create(request)
    return PlaidLinkTokenResponse(link_token=response["link_token"])


@router.post("/exchange-token")
def exchange_public_token(
    data: PlaidExchangeRequest,
    db: Session = Depends(get_db),
):
    client = get_plaid_client()

    exchange_request = ItemPublicTokenExchangeRequest(public_token=data.public_token)
    exchange_response = client.item_public_token_exchange(exchange_request)

    access_token = exchange_response["access_token"]
    item_id = exchange_response["item_id"]

    plaid_item = PlaidItem(item_id=item_id, access_token=access_token)
    db.add(plaid_item)
    db.flush()

    accounts_request = AccountsGetRequest(access_token=access_token)
    accounts_response = client.accounts_get(accounts_request)

    inst = accounts_response.get("item", {})
    inst_id = inst.get("institution_id")
    if inst_id:
        institution = db.query(Institution).filter(
            Institution.plaid_institution_id == inst_id
        ).first()
        if not institution:
            institution = Institution(
                plaid_institution_id=inst_id,
                name=inst_id,
            )
            db.add(institution)
            db.flush()
        plaid_item.institution_id = institution.id

    for acct in accounts_response["accounts"]:
        account = Account(
            plaid_account_id=acct["account_id"],
            plaid_item_id=plaid_item.id,
            institution_id=plaid_item.institution_id,
            name=acct["name"],
            official_name=acct.get("official_name"),
            account_type=acct["type"],
            account_subtype=str(acct.get("subtype", "")),
            mask=acct.get("mask"),
            current_balance=acct["balances"].get("current", 0) or 0,
            available_balance=acct["balances"].get("available"),
            currency=acct["balances"].get("iso_currency_code", "CAD") or "CAD",
        )
        db.add(account)

    db.commit()
    return {"status": "success", "item_id": item_id}


@router.post("/sync-transactions")
def sync_transactions(db: Session = Depends(get_db)):
    client = get_plaid_client()
    items = db.query(PlaidItem).filter(PlaidItem.is_active == True).all()

    total_added = 0
    for item in items:
        cursor = item.cursor
        has_more = True

        while has_more:
            request = TransactionsSyncRequest(
                access_token=item.access_token,
                cursor=cursor or "",
            )
            response = client.transactions_sync(request)

            for txn in response["added"]:
                account = db.query(Account).filter(
                    Account.plaid_account_id == txn["account_id"]
                ).first()
                if not account:
                    continue

                existing = db.query(Transaction).filter(
                    Transaction.plaid_transaction_id == txn["transaction_id"]
                ).first()
                if existing:
                    continue

                category = None
                if txn.get("personal_finance_category"):
                    category = txn["personal_finance_category"].get("primary")

                transaction = Transaction(
                    plaid_transaction_id=txn["transaction_id"],
                    account_id=account.id,
                    amount=txn["amount"],
                    currency=txn.get("iso_currency_code", "CAD") or "CAD",
                    date=txn["date"],
                    name=txn["name"],
                    merchant_name=txn.get("merchant_name"),
                    category=category,
                    pending=txn.get("pending", False),
                )
                db.add(transaction)
                total_added += 1

            cursor = response["next_cursor"]
            has_more = response["has_more"]

        item.cursor = cursor
        db.commit()

    return {"status": "success", "transactions_added": total_added}
