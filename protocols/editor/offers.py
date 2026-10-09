"""Generate plain authored Bend recipe records, never execute a workflow."""
from pathlib import Path

class Expr:
    def __init__(self, text, kind): self.text, self.kind = text, kind

def type_of(value):
    if isinstance(value, Expr): return value.kind
    if isinstance(value, dict): return '{' + ','.join(k + ':' + type_of(v) for k,v in value.items()) + '}'
    if isinstance(value, bool): return 'Bool'
    if isinstance(value, int): return 'Nat'
    return 'String'

def text(value):
    import json
    if isinstance(value, Expr): return value.text
    if isinstance(value, dict): return '{' + ','.join(k + ':' + text(v) for k,v in value.items()) + '}'
    if isinstance(value, bool): return 'true' if value else 'false'
    if isinstance(value, int): return str(value) + 'n'
    return json.dumps(value, ensure_ascii=False)

S = lambda key: Expr('state.' + key, 'String')
N = lambda key: Expr('state.' + key, 'Nat')
B = lambda value: Expr(value, 'Bool')
ref = lambda object, child='': {'object': object, 'child': child}

def call(op, object, command='', input=None, inputFrom=None):
    return {'op':op,'object':object,'command':command,'input':{} if input is None else input,
            'fromResult':inputFrom is not None,'inputFrom':0 if inputFrom is None else inputFrom}

def offer(label, command, visible, reads, calls, fields=None, bindings=None, captures=None, absent=None):
    return {'visible':visible,'title':'Workshop','label':label,'command':command,'reads':reads,
            'calls':{'c'+str(i):value for i,value in enumerate(calls)},'fields':fields or {},
            'bindings':{'b'+str(i):value for i,value in enumerate(bindings or [])},
            'absentChildren':{'a'+str(i):value for i,value in enumerate(absent or [])},
            'captures':{'s'+str(i):value for i,value in enumerate(captures or [])}}

def authored():
    own=ref('$self'); target=ref(S('target')); factory=ref(S('factory'))
    candidate={'object':Expr('if state.candidate=="" then state.factory else state.candidate','String'),
               'child':Expr('if state.candidate=="" then state.name else ""','String')}
    make=offer('Make a new variation or rebase','make',B('state.next<=32n'),
        {'editor':own,'target':target,'factory':factory},
        [call('invoke','editor','draft',{'name':''}),call('observe','target'),
         call('invoke','editor','plan',inputFrom=1),call('invoke','factory','make',inputFrom=2)],
        fields={'name':{'type':'string','label':'Variation name','minLength':1,'maxLength':64}},
        bindings=[{'field':'name','call':0,'input':'name'}],
        absent=[{'factory':'factory','field':'name'}])
    submit=offer('Submit source and examples','submit',B('state.phase=="planned"'),
        {'editor':own,'target':target,'candidate':candidate},
        [call('invoke','candidate','submit',{'proposal':{'syntax':'','source':'','scenarios':''},
            'migration':{},'target':S('target'),'editor':'','generation':N('g'),'baselineVersion':N('baseline')}),
         call('invoke','candidate','report'),call('invoke','editor','review',inputFrom=1)],
        fields={'syntax':{'type':'enum','label':'Source language','options':{'ordinary':'objective-bend-spell@2','typed':'objective-bend-spell@3'}},
                'source':{'type':'string','label':'Bend source','minLength':1,'maxLength':32768},
                'examples':{'type':'string','label':'Examples','minLength':1,'maxLength':16384}},
        bindings=[{'field':'syntax','call':0,'input':'proposal.syntax'},
                  {'field':'source','call':0,'input':'proposal.source'},
                  {'field':'examples','call':0,'input':'proposal.scenarios'}],
        captures=[{'read':'editor','call':0,'input':'editor','rootField':'object'},
                  {'read':'target','call':0,'input':'migration','rootField':'state'}])
    review=offer('Review the current candidate','review',B('state.phase=="pending"||state.phase=="ready"||state.phase=="failed"'),
        {'editor':own,'candidate':candidate},
        [call('invoke','candidate','report'),call('invoke','editor','review',inputFrom=0)])
    adopt=offer('Adopt this checked variation','adopt',B('state.phase=="ready"'),
        {'editor':own,'candidate':candidate,'target':target},
        [call('observe','target'),call('invoke','editor','approve',inputFrom=0),
         call('invoke','candidate','adopt',inputFrom=1),call('reprogram','target',inputFrom=2),
         call('invoke','editor','finish',inputFrom=3)])
    return {'make':make,'submit':submit,'review':review,'adopt':adopt}


def append_source(source):
    marker='\n# Authored captured workflow offers\n'
    source=source.split(marker)[0]
    source=source.replace('record View:', 'record BaseView:').replace('def view(state:State,panel:String)->View:',
                                                                  'def baseView(state:State,panel:String)->BaseView:')
    offers=authored()
    row=type_of(offers)
    return source+marker+'record OffersView:\n  title:String\n  prose:String\n  actions:{}\n  children:Children\n  offers:'+row+'\n'+\
        'def view(state:State,panel:String)->OffersView:\n  let prior:BaseView = baseView(state,panel)\n'+\
        '  {title:prior.title,prose:prior.prose,actions:{},children:prior.children,offers:'+text(offers)+'}\n'

if __name__=='__main__':
    path=Path(__file__).with_name('Editor.obend')
    path.write_text(append_source(path.read_text()))
