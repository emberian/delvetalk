//! Independent EffectHandler fixture against the pinned upstream runtime.
//! It deliberately does NOT roll back upstream partial effects after an error.
use serde_json::{json, Value as J};
use spween::{parse, EffectHandler, Runtime, RuntimeState, Value};
use std::{collections::{BTreeMap, BTreeSet}, io::{self, Read}, panic::{catch_unwind, AssertUnwindSafe}};

#[derive(Default)]
struct Handler {
    vars: BTreeMap<String, Value>,
    members: BTreeSet<(String, String)>,
    repairs: u64,
    emissions: Vec<J>,
}
fn tagged(v: &Value) -> J {
    match v {
        Value::Null => json!(["null"]), Value::Bool(b) => json!(["bool", b]),
        Value::Int(n) => json!(["int", n.to_string()]),
        Value::String(s) => json!(["string", s.as_str()]),
        Value::Float(f) => json!(["float", format!("{:016x}", f.to_bits())]),
    }
}
impl EffectHandler for Handler {
    fn get_var(&self, name: &str) -> Value { self.vars.get(name).cloned().unwrap_or(Value::Null) }
    fn set_var(&mut self, name: &str, value: Value) { self.vars.insert(name.into(), value); }
    fn has(&self, category: &str, key: &str) -> bool { self.members.contains(&(category.into(), key.into())) }
    fn call(&mut self, name: &str, args: &[Value]) -> Result<(), String> {
        if name == "send" {
            let [Value::String(to), Value::String(program), Value::String(chord)] = args else { return Err("send requires three strings".into()); };
            if to.is_empty() || program.is_empty() || chord.is_empty() { return Err("empty send string".into()); }
            if self.emissions.len() == 4 { return Err("emission limit".into()); }
            self.emissions.push(json!({"to":to.as_str(),"command":"hear","recipientProgram":program.as_str(),"payload":{"chord":chord.as_str()}}));
            return Ok(());
        }
        if !args.is_empty() { return Err("local handler takes no arguments".into()); }
        match name {
            "repair" => { self.set_var("work", Value::Int(10)); self.members.insert(("inventory".into(),"moth".into())); self.repairs += 1; Ok(()) },
            "release" => { self.members.remove(&("inventory".into(), "moth".into())); Ok(()) },
            "reject" => Err("handler declined".into()),
            _ => Err("unknown handler command".into()),
        }
    }
}
fn snapshot(r: &Runtime<'_, Handler>) -> J {
    json!({"vars":r.handler().vars.iter().map(|(k,v)|(k.clone(),tagged(v))).collect::<BTreeMap<_,_>>(),
        "members":r.handler().members,"repairs":r.handler().repairs,"emissions":r.handler().emissions,
        "ended":r.is_ended(),"passage":match r.state(){RuntimeState::Running(n)=>Some(*n),RuntimeState::Ended=>None},
        "choices":r.current_choices().iter().map(|c|json!({"index":c.index,"available":c.available})).collect::<Vec<_>>()})
}
fn main() {
    let mut raw=String::new(); io::stdin().read_to_string(&mut raw).unwrap();
    let input:J=serde_json::from_str(&raw).unwrap();
    let scene=parse(input["source"].as_str().unwrap(), "handler-oracle.scene").unwrap();
    // Initial-failure fixtures use a plain intro so real partial state remains inspectable.
    let mut runtime=Runtime::new(&scene, Handler::default()).unwrap();
    let mut trace=vec![json!({"kind":"ok","snapshot":snapshot(&runtime)})];
    for choice in input["choices"].as_array().unwrap() {
        runtime.handler_mut().emissions.clear();
        let result=catch_unwind(AssertUnwindSafe(||runtime.select_choice(choice.as_u64().unwrap() as usize)));
        let (kind,error)=match result {Ok(Ok(()))=>("ok",J::Null),Ok(Err(e))=>("error",json!(e.to_string())),Err(_)=>("panic",json!("checked arithmetic overflow"))};
        trace.push(json!({"kind":kind,"error":error,"snapshot":snapshot(&runtime)}));
    }
    println!("{}",json!({"upstream":"95980f7d1e109138496849a444f28c4b9076a4e2","trace":trace}));
}
