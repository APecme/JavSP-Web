"""Authenticated read APIs; bounded outbound work only on explicit POSTs."""
from typing import Literal

from fastapi import APIRouter, Depends, Response
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


# Clash control is administrator-only and never accepts arbitrary target URLs.
from . import hot_clash
from fastapi import HTTPException
from pydantic import Field


class ClashStartBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    controller_url: str = Field(max_length=1024)
    secret: str = Field(default='', max_length=512)
    proxy_url: str = Field(max_length=1024)
    source_ids: list[str] = Field(min_length=1, max_length=3)
    confirm_switch: bool = False


class ClashExportBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    original_yaml: str = Field(max_length=1_000_000)
    selected_nodes: list[str] = Field(min_length=1, max_length=100)
    job_id: str = Field(max_length=64)


@router.get('/clash')
def clash_status(response: Response, _: dict = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    return hot_clash.status()


@router.post('/clash', status_code=202)
def clash_start(body: ClashStartBody, response: Response, _: dict = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return hot_clash.start(body.controller_url, body.secret, body.proxy_url,
                               body.source_ids, body.confirm_switch)
    except hot_clash.ClashError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@router.post('/clash/cancel')
def clash_cancel(response: Response, _: dict = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    return hot_clash.cancel()


@router.post('/clash/export')
def clash_export(body: ClashExportBody, _: dict = Depends(require_admin)):
    try:
        result = hot_clash.export_yaml(body.original_yaml, body.selected_nodes, body.job_id)
        return Response(result, media_type='application/yaml', headers={
            'Cache-Control': 'no-store', 'Content-Disposition': 'attachment; filename="javsp-clash.yaml"'})
    except hot_clash.ClashError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
