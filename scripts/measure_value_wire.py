import json

def rec(fields): return {'tag':'record','fields':[{'name':k,'value':v} for k,v in fields]}
def var(k,fields): return {'tag':'variant','label':k,'payload':rec(fields)}
def value(v):
 if v is None:return var('none',[])
 if isinstance(v,bool):return var('boolean',[('value',{'tag':'boolean','value':v})])
 if isinstance(v,str):return var('text',[('value',{'tag':'label','value':v})])
 if isinstance(v,int):return var('natural',[('value',{'tag':'natural','value':str(v)})])
 pairs=list(v.items()) if isinstance(v,dict) else list(enumerate(v))
 tail=var('nil',[])
 for k,x in reversed(pairs):
  head=rec([('name',{'tag':'label','value':k}),('value',value(x))]) if isinstance(v,dict) else value(x)
  tail=var('cons',[('head',head),('tail',tail)])
 return var('record' if isinstance(v,dict) else 'array',[('fields' if isinstance(v,dict) else 'values',tail)])
def count(v):return 1+sum(map(count,v.values())) if isinstance(v,dict) else 1+sum(map(count,v)) if isinstance(v,list) else 1
def size(v):return len(json.dumps(v,separators=(',',':'),ensure_ascii=False).encode())
fixtures={'document':{'title':'Notes','blocks':[{'kind':'paragraph','text':'A paragraph of useful content.'} for _ in range(20)]},'scene':{'title':'Courtyard','children':[{'kind':'button','label':'Open','action':{'object':'notebook','command':'read'}} for _ in range(12)]},'candidate64KiB':{'name':'Candidate','modules':[{'name':'Resident','source':'x'*65536}]},'gallery200':[{'title':f'Page {n}','body':'A page in the gallery.','id':n} for n in range(200)]}
for name,v in fixtures.items():
 wire=value(v)
 print(name,json.dumps({'plainBytes':size(v),'plainJsonNodes':count(v),'valueWireBytes':size(wire),'valueWireJsonNodes':count(wire)}))
