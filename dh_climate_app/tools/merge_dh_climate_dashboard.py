#!/usr/bin/env python3
"""Non-destructive merge of DH Climate views into an exported Lovelace YAML.

Does not access Home Assistant, does not overwrite an existing file,
and never modifies the first view or unrelated views. Only paths
'climate', 'outdoor' and 'admin' are replaceable.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from pathlib import Path
import yaml

ALLOWED={'climate','outdoor','admin'}

def merge(existing:dict, addon:dict)->tuple[dict,list[str],list[str]]:
    if not isinstance(existing,dict) or not isinstance(existing.get('views'),list):
        raise ValueError('В экспортированном dashboard отсутствует список views')
    if not isinstance(addon,dict) or not isinstance(addon.get('views'),list):
        raise ValueError('Отсутствует файл дополнительных views')
    out=deepcopy(existing)
    paths={}
    for idx, view in enumerate(out['views']):
        if not isinstance(view,dict): raise ValueError('В existing.views найден некорректный view')
        key=view.get('path')
        if key and key in paths: raise ValueError(f'Дублируется path в существующем YAML: {key}')
        if key: paths[key]=idx
    replaced=[];added=[]
    for entry in addon['views']:
        key=entry.get('path')
        if key not in ALLOWED: raise ValueError(f'Запрещено обновлять view: {key}')
        if key in paths:
            out['views'][paths[key]]=deepcopy(entry)
            replaced.append(key)
        else:
            out['views'].append(deepcopy(entry))
            added.append(key)
    # Default/first view and all non-Climate views must remain intact.
    if out['views'][0]!=existing['views'][0] and existing['views'][0].get('path') not in ALLOWED:
        raise AssertionError('Первый dashboard изменён: операция отменена')
    if len(out['views'])!=len(existing['views'])+len(added):
        raise AssertionError('Количество страниц неожиданно изменилось')
    return out, replaced, added

def main()->None:
    p=argparse.ArgumentParser(description='DH Climate · объединить dashboard без изменения HA')
    p.add_argument('existing',type=Path,help='Экспорт текущего DH Climate (raw YAML)')
    p.add_argument('--overlay',type=Path,default=Path(__file__).with_name('dh_climate_dashboard_add_views_0.2.yaml'))
    p.add_argument('--out',type=Path,required=True,help='Новый файл, не оригинал')
    args=p.parse_args()
    if args.out.exists(): p.error('Файл результата уже существует; перезапись запрещена')
    if args.out.resolve()==args.existing.resolve():p.error('Нельзя перезаписывать текущий dashboard')
    with args.existing.open(encoding='utf-8') as f: current=yaml.safe_load(f)
    with args.overlay.open(encoding='utf-8') as f:overlay=yaml.safe_load(f)
    output,replaced,added=merge(current,overlay)
    with args.out.open('x',encoding='utf-8') as f:
        f.write('# DH Climate · объединённый Lovelace. Текущий dashboard не изменён.\n')
        yaml.safe_dump(output,f,allow_unicode=True,sort_keys=False,width=2000)
    print('REPLACED:',', '.join(replaced) or '-')
    print('ADDED:',', '.join(added) or '-')
    print('OUTPUT:',args.out)

if __name__=='__main__':main()