"""Authenticated read APIs; bounded outbound work only on explicit POSTs."""
from typing import Literal

from fastapi import APIRouter, Depends, Response, HTTPException
from pydantic import BaseModel, ConfigDict

from . import hot
from .auth import current_user, require_admin

router = APIRouter(prefix='/api/hot', dependencies=[Depends(current_user)])
Category = Literal['all', 'censored', 'uncensored']
Sort = Literal['latest', 'hot']


class RefreshBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Category = 'all'
    sort: Sort = 'latest'


class CheckBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


@router.get('/connections')
def get_connections(response: Response, user: dict = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return dict(hot.connections(), can_check=user.get('role') == 'admin')


@router.post('/connections', status_code=202)
def check_connections(body: CheckBody, response: Response, _: dict = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    return dict(hot.start_checks(), can_check=True)


@router.get('/films')
def get_films(response: Response, category: Category = 'all', sort: Sort = 'latest'):
    response.headers['Cache-Control'] = 'no-store'
    return hot.films(category, sort)


@router.post('/refresh', status_code=202)
def refresh(body: RefreshBody, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return hot.refresh_films(body.category, body.sort)



class AgeConfirmBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmed: bool = False


@router.post('/age/{source_id}', status_code=202)
def confirm_age(source_id: str, body: AgeConfirmBody, response: Response,
                _: dict = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return hot.confirm_age(source_id, body.confirmed)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
