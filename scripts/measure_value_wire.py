#!/usr/bin/env python3
"""Representation measurement, not an application codec.
Supply --binary to check model bytes against the actual native Value codec.
Fixtures are deliberately explicit representative structures, not live data.
"""
import argparse
import subprocess
import time
import json

def rec(fields): return {'tag':'record','fields':[{'name':k,'value':v} for k,v in fields]}
def var(k,fields): return {'tag':'variant','label':k,'payload':rec(fields)}
def value(v):
 if v is None:return var('none',[])
 if isinstance(v,bool):return var('boolean',[('value',{'tag':'boolean','value':v})])
 if isinstance(v,str):return var('text',[('value',{'tag':'label','value':v})])
 if isinstance(v,int):return var('natural',[('value',{'tag':'natural','value':str(v)})])
 pairs=sorted(v.items()) if isinstance(v,dict) else list(enumerate(v))
 tail=var('nil',[])
 for k,x in reversed(pairs):
  head=rec([('name',{'tag':'label','value':k}),('value',value(x))]) if isinstance(v,dict) else value(x)
  tail=var('cons',[('head',head),('tail',tail)])
 return var('record' if isinstance(v,dict) else 'array',[('fields' if isinstance(v,dict) else 'values',tail)])
def compact_data(wire):
 # Measurement only: fixture schemas use canonical alphabetical record rows.
 tag=wire['tag']
 if tag in ('natural','boolean','label'):return wire['value']
 if tag=='variant':return [wire['label'],compact_data(wire['payload'])]
 return [compact_data(field['value']) for field in sorted(wire['fields'],key=lambda f:f['name'])]
def count(v):return 1+sum(map(count,v.values())) if isinstance(v,dict) else 1+sum(map(count,v)) if isinstance(v,list) else 1
def size(v):return len(json.dumps(v,separators=(',',':'),ensure_ascii=False).encode())
fixtures={'document':{'title':'Notes','blocks':[{'kind':'paragraph','text':'A paragraph of useful content.'} for _ in range(20)]},'scene':{'title':'Courtyard','children':[{'kind':'button','label':'Open','action':{'object':'notebook','command':'read'}} for _ in range(12)]},'candidate64KiB':{'name':'Candidate','modules':[{'name':'Resident','source':'x'*65536}]},'gallery200':[{'title':f'Page {n}','body':'A page in the gallery.','id':n} for n in range(200)]}
parser=argparse.ArgumentParser()
parser.add_argument("--binary")
args=parser.parse_args()
for name,v in fixtures.items():
 wire=value(v)
 compact=compact_data(wire)
 row={'compactBytes':size(compact),'compactJsonNodes':count(compact),'plainBytes':size(v),'plainJsonNodes':count(v),'valueWireBytes':size(wire),'valueWireJsonNodes':count(wire)}
 if args.binary:
  request={'world':{'objects':{},'receipts':[]},'request':{'op':'value-codec','direction':'encode','values':[v]}}
  started=time.perf_counter()
  done=subprocess.run([args.binary],input=json.dumps(request)+'\n',text=True,capture_output=True,check=True)
  row['nativeFreshMillis']=round((time.perf_counter()-started)*1000,3)
  actual=json.loads(done.stdout)['reply']['values'][0]
  assert actual==wire, (name,'native Value differs from source model')
  row['nativeVerified']=True
 print(name,json.dumps(row))
