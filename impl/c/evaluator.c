/* DelveTalk reference tree reducer. Dependencies: C11, GMP, json-c >= 0.15.
 * No memoization: every reduction follows the upstream call-by-name Step.
 * JSON nodes are immutable after construction and reference counted. */
#define _POSIX_C_SOURCE 200809L
#include <json-c/json.h>
#include <gmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <ctype.h>

typedef struct json_object J;
#define AT(t,i) json_object_array_get_idx((t),(i))
#define LEN(t) json_object_array_length(t)
#define SAFE UINT64_C(9007199254740991)
static void fail(const char *s) { fprintf(stderr,"delvetalk-c: %s\n",s); exit(2); }
static J *keep(J *x) { return json_object_get(x); }
static const char *str(J *x) { return json_object_get_string(x); }
static int eq(J *a,J *b) {
 return json_object_get_string_len(a)==json_object_get_string_len(b) &&
 !memcmp(str(a),str(b),(size_t)json_object_get_string_len(a));
}
static int tag(J *t,const char *s) { return !strcmp(str(AT(t,0)),s); }
static J *arr(void) { J *r=json_object_new_array(); if(!r) fail("allocation failure"); return r; }
static void add(J *a,J *v) { if(json_object_array_add(a,v)) fail("allocation failure"); }
static J *one(const char *s,J *a) { J *r=arr(); add(r,json_object_new_string(s)); add(r,a); return r; }
static J *two(const char *s,J *a,J *b) { J *r=one(s,a); add(r,b); return r; }
static J *replace(J *t,size_t slot,J *v) {
 J *r=arr(); for(size_t i=0;i<LEN(t);i++) add(r,i==slot?v:keep(AT(t,i))); return r;
}
static int isstr(J *v) { return json_object_is_type(v,json_type_string); }
static int isint(J *v) { return json_object_is_type(v,json_type_int) && json_object_get_int64(v)>=0 && json_object_get_uint64(v)<=SAFE; }
static int named(J *v,const char *names) {
 if(!isstr(v)||strchr(str(v),' ')||strlen(str(v))!=(size_t)json_object_get_string_len(v)) return 0;
 const char *p=names; size_t n=strlen(str(v));
 while(*p) { size_t k=strcspn(p," "); if(k==n&&!strncmp(p,str(v),n)) return 1; p+=k; if(*p) p++; } return 0;
}
static void validate(J *t);
static void fields(J *fs) {
 if(!json_object_is_type(fs,json_type_array)) fail("fields/arms must be arrays");
 for(size_t i=0;i<LEN(fs);i++) { J *f=AT(fs,i); if(!json_object_is_type(f,json_type_array)||LEN(f)!=2||!isstr(AT(f,0))) fail("invalid field/arm"); validate(AT(f,1)); }
}
static void validate(J *t) {
 if(!json_object_is_type(t,json_type_array)||LEN(t)<2||!isstr(AT(t,0))) fail("invalid term array");
 if(!named(AT(t,0),"bound lam app mix fix specification prototype reflect metadata project nat boolean label binary unary extend record get ifZero inject case ifBool perform done")) fail("unknown term constructor");
 J *a=AT(t,1); size_t n=LEN(t);
 if(tag(t,"bound")) { if(n!=2||!isint(a)) fail("invalid bound index"); }
 else if(tag(t,"nat")) {
  if(n!=2||!isstr(a)) fail("natural must be decimal string");
  size_t k=(size_t)json_object_get_string_len(a); const char *s=str(a);
  if(!k||(k>1&&s[0]=='0')) fail("noncanonical natural");
  for(size_t i=0;i<k;i++) if(s[i]<'0'||s[i]>'9') fail("invalid natural");
 } else if(tag(t,"boolean")) { if(n!=2||!json_object_is_type(a,json_type_boolean)) fail("invalid boolean"); }
 else if(tag(t,"label")) { if(n!=2||!isstr(a)) fail("invalid label"); }
 else if(named(AT(t,0),"lam reflect metadata project perform done")) { if(n!=2) fail("wrong unary arity"); validate(a); }
 else if(named(AT(t,0),"app mix fix specification prototype")) { if(n!=3) fail("wrong binary arity"); validate(a); validate(AT(t,2)); }
 else if(tag(t,"record")) { if(n!=2) fail("wrong record arity"); fields(a); }
 else if(tag(t,"extend")||tag(t,"case")) { if(n!=3) fail("wrong field operation arity"); validate(a); fields(AT(t,2)); }
 else if(tag(t,"get")) { if(n!=3||!isstr(AT(t,2))) fail("invalid get"); validate(a); }
 else if(tag(t,"inject")) { if(n!=3||!isstr(a)) fail("invalid inject"); validate(AT(t,2)); }
 else if(tag(t,"binary")) {
  if(n!=4||!named(a,"add multiply equal conjunction labelEqual subtract divide less lessEqual modulo textConcat textTake textDrop textSpan textBreak")) fail("invalid primitive"); validate(AT(t,2)); validate(AT(t,3));
 } else if(tag(t,"unary")) {
  if(n!=3||!named(a,"natText textLength sha256Text")) fail("invalid unary primitive"); validate(AT(t,2));
 } else if(tag(t,"ifZero")||tag(t,"ifBool")) { if(n!=4) fail("wrong condition arity"); validate(a); validate(AT(t,2)); validate(AT(t,3)); }
 else fail("unknown term constructor");
}
static int value(J *t) { return named(AT(t,0),"lam nat boolean label record specification prototype inject"); }
/* mode=0: raise free indices by delta; mode=1: instantiate at depth. */
static J *walk(J *t,uint64_t depth,int mode,uint64_t delta,J *arg);
static J *walkfields(J *fs,uint64_t depth,int mode,uint64_t delta,J *arg) {
 J *r=arr(); for(size_t i=0;i<LEN(fs);i++) { J *f=AT(fs,i),*pair=arr(); add(pair,keep(AT(f,0))); add(pair,walk(AT(f,1),depth,mode,delta,arg)); add(r,pair); } return r;
}
static J *walk(J *t,uint64_t depth,int mode,uint64_t delta,J *arg) {
 if(tag(t,"bound")) {
  uint64_t k=json_object_get_uint64(AT(t,1)); if(k<depth) return keep(t);
  if(mode&&k==depth) return walk(arg,0,0,depth,NULL);
  if(!mode&&k>SAFE-delta) fail("bound index exceeds portable wire range");
  return one("bound",json_object_new_uint64(mode?k-1:k+delta));
 }
 if(named(AT(t,0),"nat boolean label")) return keep(t);
 J *r=arr(); add(r,keep(AT(t,0)));
 for(size_t i=1;i<LEN(t);i++) {
  int fs=(tag(t,"record")&&i==1)||((tag(t,"extend")||tag(t,"case"))&&i==2);
  int literal=((tag(t,"binary")||tag(t,"unary"))&&i==1)||(tag(t,"get")&&i==2)||(tag(t,"inject")&&i==1);
  uint64_t d=depth+((tag(t,"lam")&&i==1)||(tag(t,"ifZero")&&i==3)||(tag(t,"case")&&i==2));
  add(r,literal?keep(AT(t,i)):fs?walkfields(AT(t,i),d,mode,delta,arg):walk(AT(t,i),d,mode,delta,arg));
 } return r;
}
static J *inst(J *body,J *arg) { return walk(body,0,1,0,arg); }
static J *lookup(J *fs,J *name) { for(size_t i=0;i<LEN(fs);i++) if(eq(AT(AT(fs,i),0),name)) return AT(AT(fs,i),1); return NULL; }
static J *natural(mpz_t z) { char *s=mpz_get_str(NULL,10,z); J *r=one("nat",json_object_new_string(s)); void (*release)(void *,size_t); mp_get_memory_functions(NULL,NULL,&release); release(s,strlen(s)+1); return r; }

/* ---- text: code points (UTF-8), SHA-256 ---- */
static size_t u8count(const char *s,size_t n) { size_t k=0; for(size_t i=0;i<n;i++) if(((unsigned char)s[i]&0xc0)!=0x80) k++; return k; }
static size_t u8width(unsigned char c) { return c<0x80?1:c<0xe0?2:c<0xf0?3:4; }
/* byte offset of the k-th code point, or n when k reaches the end */
static size_t u8offset(const char *s,size_t n,size_t k) { size_t i=0; while(k&&i<n) { i+=u8width((unsigned char)s[i]); k--; } return i<n?i:n; }
static int in_alphabet(const char *c,size_t w,const char *alpha,size_t an) {
 for(size_t i=0;i<an;i+=u8width((unsigned char)alpha[i])) { size_t aw=u8width((unsigned char)alpha[i]); if(aw==w&&!memcmp(alpha+i,c,w)) return 1; } return 0;
}
static J *label_n(const char *s,size_t n) { return one("label",json_object_new_string_len(s,(int)n)); }
static J *nat_u64(uint64_t v) { mpz_t z; mpz_init_set_ui(z,v); J *r=natural(z); mpz_clear(z); return r; }
static uint32_t rotr(uint32_t x,int k) { return (x>>k)|(x<<(32-k)); }
static void sha256_hex(const unsigned char *msg,size_t len,char out[65]) {
 static const uint32_t K[64]={0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
 uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
 size_t total=((len+8)/64+1)*64; unsigned char *m=calloc(total,1); if(!m) fail("allocation failure");
 memcpy(m,msg,len); m[len]=0x80; uint64_t bits=(uint64_t)len*8; for(int i=0;i<8;i++) m[total-1-i]=(unsigned char)(bits>>(8*i));
 for(size_t off=0;off<total;off+=64) {
  uint32_t w[64]; for(int i=0;i<16;i++) w[i]=(uint32_t)m[off+4*i]<<24|(uint32_t)m[off+4*i+1]<<16|(uint32_t)m[off+4*i+2]<<8|m[off+4*i+3];
  for(int i=16;i<64;i++) { uint32_t s0=rotr(w[i-15],7)^rotr(w[i-15],18)^(w[i-15]>>3),s1=rotr(w[i-2],17)^rotr(w[i-2],19)^(w[i-2]>>10); w[i]=w[i-16]+s0+w[i-7]+s1; }
  uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
  for(int i=0;i<64;i++) { uint32_t S1=rotr(e,6)^rotr(e,11)^rotr(e,25),ch=(e&f)^(~e&g),t1=hh+S1+ch+K[i]+w[i],S0=rotr(a,2)^rotr(a,13)^rotr(a,22),mj=(a&b)^(a&c)^(b&c),t2=S0+mj; hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2; }
  h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh;
 }
 free(m); for(int i=0;i<8;i++) sprintf(out+8*i,"%08x",h[i]);
}
static J *text_primitive(const char *op,J *a,J *b) {
 if(!strcmp(op,"textConcat")||!strcmp(op,"textSpan")||!strcmp(op,"textBreak")) {
  if(!tag(a,"label")||!tag(b,"label")) return NULL;
  const char *x=str(AT(a,1)),*y=str(AT(b,1)); size_t xn=(size_t)json_object_get_string_len(AT(a,1)),yn=(size_t)json_object_get_string_len(AT(b,1));
  if(!strcmp(op,"textConcat")) { char *buf=malloc(xn+yn+1); if(!buf) fail("allocation failure"); memcpy(buf,x,xn); memcpy(buf+xn,y,yn); J *r=label_n(buf,xn+yn); free(buf); return r; }
  int member=!strcmp(op,"textSpan"); uint64_t count=0;
  for(size_t i=0;i<xn;i+=u8width((unsigned char)x[i])) { size_t w=u8width((unsigned char)x[i]); if(in_alphabet(x+i,w,y,yn)!=member) break; count++; }
  return nat_u64(count);
 }
 if(!tag(a,"label")||!tag(b,"nat")) return NULL;
 const char *x=str(AT(a,1)); size_t xn=(size_t)json_object_get_string_len(AT(a,1));
 mpz_t n; mpz_init_set_str(n,str(AT(b,1)),10); int zero=!mpz_sgn(n), big=mpz_cmp_ui(n,xn)>=0; size_t k=big?xn:mpz_get_ui(n); mpz_clear(n);
 int take=!strcmp(op,"textTake");
 if(take) return zero?label_n("",0):big?label_n(x,xn):label_n(x,u8offset(x,xn,k));
 return zero?label_n(x,xn):big?label_n("",0):label_n(x+u8offset(x,xn,k),xn-u8offset(x,xn,k));
}
static J *unary_primitive(J *t) {
 const char *op=str(AT(t,1)); J *a=AT(t,2);
 if(!strcmp(op,"natText")) return tag(a,"nat")?one("label",json_object_new_string(str(AT(a,1)))):NULL;
 if(!tag(a,"label")) return NULL;
 const char *x=str(AT(a,1)); size_t xn=(size_t)json_object_get_string_len(AT(a,1));
 if(!strcmp(op,"textLength")) return nat_u64(u8count(x,xn));
 char hex[65]; sha256_hex((const unsigned char *)x,xn,hex); return one("label",json_object_new_string(hex));
}
static J *primitive(J *t) {
 J *a=AT(t,2),*b=AT(t,3); const char *op=str(AT(t,1));
 if(!strcmp(op,"conjunction")) return tag(a,"boolean")&&tag(b,"boolean")?one("boolean",json_object_new_boolean(json_object_get_boolean(AT(a,1))&&json_object_get_boolean(AT(b,1)))):NULL;
 if(!strcmp(op,"labelEqual")) return tag(a,"label")&&tag(b,"label")?one("boolean",json_object_new_boolean(eq(AT(a,1),AT(b,1)))):NULL;
 if(!strncmp(op,"text",4)) return text_primitive(op,a,b);
 if(!tag(a,"nat")||!tag(b,"nat")) return NULL;
 mpz_t x,y,z; mpz_inits(x,y,z,NULL); mpz_set_str(x,str(AT(a,1)),10); mpz_set_str(y,str(AT(b,1)),10); J *r=NULL;
 if(!strcmp(op,"equal")||!strcmp(op,"less")||!strcmp(op,"lessEqual")) { int c=mpz_cmp(x,y); r=one("boolean",json_object_new_boolean(!strcmp(op,"equal")?c==0:!strcmp(op,"less")?c<0:c<=0)); }
 else {
  if(!strcmp(op,"add")) mpz_add(z,x,y);
  else if(!strcmp(op,"multiply")) mpz_mul(z,x,y);
  else if(!strcmp(op,"subtract")) { if(mpz_cmp(x,y)>=0) mpz_sub(z,x,y); }
  else if(!strcmp(op,"divide")) { if(mpz_sgn(y)) mpz_fdiv_q(z,x,y); }
  else if(!strcmp(op,"modulo")) { if(mpz_sgn(y)) mpz_mod(z,x,y); else mpz_set(z,x); }
  r=natural(z);
 } mpz_clears(x,y,z,NULL); return r;
}
enum Kind { STUCK, STEP, YIELD };
typedef struct { enum Kind kind; J *next; J *plan; } Transition;
static Transition result(J *t) { return (Transition){t?STEP:STUCK,t,NULL}; }
/* Inspect Step's premises without constructing its conclusion. At zero fuel,
 * even a disabled beta/mix expansion or arithmetic operation must not run:
 * it could exceed the wire representation or allocate an enormous term. */
static int reducible(J *t) {
 J *a=AT(t,1),*b=AT(t,2);
 if(tag(t,"done")||tag(t,"fix")||tag(t,"mix")) return 1;
 if(tag(t,"app")) return tag(a,"lam")||tag(a,"specification")||reducible(a);
 if(tag(t,"reflect")||tag(t,"project")) return tag(a,"prototype")||reducible(a);
 if(tag(t,"metadata")) return tag(a,"specification")||reducible(a);
 if(tag(t,"get")) return tag(a,"record")?lookup(AT(a,1),b)!=NULL:reducible(a);
 if(tag(t,"extend")) return tag(a,"record")||reducible(a);
 if(tag(t,"binary")) {
  J *right=AT(t,3);
  if(!value(b)) return reducible(b);
  if(!value(right)) return reducible(right);
  if(!strcmp(str(a),"conjunction")) return tag(b,"boolean")&&tag(right,"boolean");
  if(!strcmp(str(a),"labelEqual")) return tag(b,"label")&&tag(right,"label");
  if(!strcmp(str(a),"textConcat")||!strcmp(str(a),"textSpan")||!strcmp(str(a),"textBreak")) return tag(b,"label")&&tag(right,"label");
  if(!strcmp(str(a),"textTake")||!strcmp(str(a),"textDrop")) return tag(b,"label")&&tag(right,"nat");
  return tag(b,"nat")&&tag(right,"nat");
 }
 if(tag(t,"unary")) {
  if(!value(b)) return reducible(b);
  return !strcmp(str(a),"natText")?tag(b,"nat"):tag(b,"label");
 }
 if(tag(t,"ifZero")) return tag(a,"nat")||reducible(a);
 if(tag(t,"ifBool")) return tag(a,"boolean")||reducible(a);
 if(tag(t,"case")) return tag(a,"inject")?lookup(b,AT(a,1))!=NULL:reducible(a);
 return 0;
}
static Transition advance(J *t,J *response);
static Transition context(J *t,size_t pos,J *response) {
 Transition r=advance(AT(t,pos),response); if(r.next) r.next=replace(t,pos,r.next); return r;
}
static Transition advance(J *t,J *response) {
 J *a=AT(t,1),*b=AT(t,2);
 if(tag(t,"perform")) return (Transition){YIELD,response?keep(response):NULL,keep(a)};
 if(tag(t,"done")) return result(keep(a));
 if(tag(t,"app")) {
  if(tag(a,"lam")) return result(inst(AT(a,1),b));
  if(tag(a,"specification")) return result(two("app",keep(AT(a,2)),keep(b)));
  return context(t,1,response);
 }
 if(tag(t,"fix")) return result(two("app",two("app",keep(a),keep(t)),keep(b)));
 if(tag(t,"mix")) {
  J *lower=walk(a,0,0,2,NULL),*upper=walk(b,0,0,2,NULL);
  J *self=one("bound",json_object_new_int(1));
  J *body=two("app",two("app",upper,keep(self)),two("app",two("app",lower,self),one("bound",json_object_new_int(0))));
  return result(one("lam",one("lam",body)));
 }
 if(tag(t,"reflect")||tag(t,"project")) { if(tag(a,"prototype")) return result(keep(AT(a,tag(t,"reflect")?1:2))); return context(t,1,response); }
 if(tag(t,"metadata")) { if(tag(a,"specification")) return result(keep(AT(a,1))); return context(t,1,response); }
 if(tag(t,"get")) { if(tag(a,"record")) { J *v=lookup(AT(a,1),b); return result(v?keep(v):NULL); } return context(t,1,response); }
 if(tag(t,"extend")) {
  if(tag(a,"record")) { J *fs=arr(),*old=AT(a,1); for(size_t i=0;i<LEN(b);i++) add(fs,keep(AT(b,i))); for(size_t i=0;i<LEN(old);i++) if(!lookup(b,AT(AT(old,i),0))) add(fs,keep(AT(old,i))); return result(one("record",fs)); } return context(t,1,response);
 }
 if(tag(t,"binary")) { if(!value(b)) return context(t,2,response); if(!value(AT(t,3))) return context(t,3,response); return result(primitive(t)); }
 if(tag(t,"unary")) { if(!value(b)) return context(t,2,response); return result(unary_primitive(t)); }
 if(tag(t,"ifZero")) {
  if(tag(a,"nat")) { mpz_t z; mpz_init_set_str(z,str(AT(a,1)),10); J *r; if(!mpz_sgn(z)) r=keep(b); else { mpz_sub_ui(z,z,1); J *n=natural(z); r=inst(AT(t,3),n); json_object_put(n); } mpz_clear(z); return result(r); } return context(t,1,response);
 }
 if(tag(t,"ifBool")) { if(tag(a,"boolean")) return result(keep(AT(t,json_object_get_boolean(AT(a,1))?2:3))); return context(t,1,response); }
 if(tag(t,"case")) { if(tag(a,"inject")) { J *body=lookup(b,AT(a,1)); return result(body?inst(body,AT(a,2)):NULL); } return context(t,1,response); }
 return result(NULL);
}
static J *run(J *job) {
 if(!json_object_is_type(job,json_type_object)) fail("job must be object");
 J *name=NULL,*t=NULL,*responses=NULL,*fuel=NULL;
 if(!json_object_object_get_ex(job,"name",&name)||!isstr(name)||!json_object_object_get_ex(job,"term",&t)) fail("job needs string name and term");
 if(!json_object_object_get_ex(job,"fuel",&fuel)) { fuel=json_object_new_int(10000); json_object_object_add(job,"fuel",fuel); }
 if(!isint(fuel)) fail("fuel must be nonnegative safe integer");
 if(!json_object_object_get_ex(job,"responses",&responses)) { responses=arr(); json_object_object_add(job,"responses",responses); }
 if(!json_object_is_type(responses,json_type_array)) fail("responses must be array");
 json_object_object_foreach(job,key,val) { (void)val; if(strcmp(key,"name")&&strcmp(key,"term")&&strcmp(key,"fuel")&&strcmp(key,"responses")) fail("unknown job field"); }
 validate(t); for(size_t i=0;i<LEN(responses);i++) validate(AT(responses,i));
 t=keep(t); J *plans=arr(); uint64_t remaining=json_object_get_uint64(fuel); size_t ri=0; const char *status;
 for(;;) {
  if(value(t)) { status="value"; break; }
  if(!remaining&&reducible(t)) { status="exhausted"; break; }
  Transition r=advance(t,ri<LEN(responses)?AT(responses,ri):NULL);
  if(r.kind==YIELD) { add(plans,r.plan); if(!r.next) { status="yield"; break; } ri++; json_object_put(t); t=r.next; continue; }
  if(r.kind==STUCK) { status="stuck"; break; }
  if(!remaining) { json_object_put(r.next); status="exhausted"; break; }
  remaining--; json_object_put(t); t=r.next;
 }
 J *out=json_object_new_object(); json_object_object_add(out,"name",keep(name)); json_object_object_add(out,"status",json_object_new_string(status)); json_object_object_add(out,"term",t); json_object_object_add(out,"plans",plans); return out;
}
/* json-c replaces lone escaped surrogates with U+FFFD. Reject them before
 * decoding so an invalid scalar string cannot silently become another label. */
static unsigned hex4(const char *s,size_t available) {
 if(available<4) fail("incomplete Unicode escape");
 unsigned r=0;
 for(size_t i=0;i<4;i++) {
  unsigned c=(unsigned char)s[i],v;
  if(c>='0'&&c<='9') v=c-'0'; else if(c>='a'&&c<='f') v=c-'a'+10;
  else if(c>='A'&&c<='F') v=c-'A'+10; else { fail("invalid Unicode escape"); v=0; }
  r=16*r+v;
 } return r;
}
static void scalar_escapes(const char *s,size_t n) {
 int quoted=0,nul=0;
 for(size_t i=0;i<n;i++) {
  if(s[i]=='"') {
   if(quoted&&nul) { size_t j=i+1; while(j<n&&isspace((unsigned char)s[j])) j++; if(j<n&&s[j]==':') fail("NUL in object key"); }
   quoted=!quoted; nul=0; continue;
  }
  if(!quoted||s[i]!='\\') continue;
  if(++i>=n) fail("incomplete string escape");
  if(s[i]!='u') continue;
  unsigned c=hex4(s+i+1,n-i-1); i+=4;
  if(!c) nul=1;
  if(c>=0xdc00&&c<=0xdfff) fail("unpaired low surrogate");
  if(c>=0xd800&&c<=0xdbff) {
   if(n-i-1<6||s[i+1]!='\\'||s[i+2]!='u') fail("unpaired high surrogate");
   unsigned d=hex4(s+i+3,n-i-3);
   if(d<0xdc00||d>0xdfff) fail("unpaired high surrogate");
   i+=6;
  }
 }
}
/* json-c's UTF-8 flag checks continuation shape but permits some non-scalars.
 * Keep the wire alphabet exactly Unicode scalar values, including raw UTF-8. */
static void scalar_utf8(const unsigned char *s,size_t n) {
 for(size_t i=0;i<n;i++) {
  unsigned c=s[i],need,min;
  if(c<0x80) continue;
  if(c>=0xc2&&c<=0xdf) { need=1; min=0x80; c&=0x1f; }
  else if(c>=0xe0&&c<=0xef) { need=2; min=0x800; c&=0x0f; }
  else if(c>=0xf0&&c<=0xf4) { need=3; min=0x10000; c&=7; }
  else { fail("invalid UTF-8"); return; }
  if(n-i-1<need) fail("incomplete UTF-8");
  while(need--) { unsigned b=s[++i]; if((b&0xc0)!=0x80) fail("invalid UTF-8 continuation"); c=(c<<6)|(b&0x3f); }
  if(c<min||c>0x10ffff||(c>=0xd800&&c<=0xdfff)) fail("non-scalar UTF-8");
 }
}
int main(void) {
 char *line=NULL; size_t cap=0; ssize_t n;
 while((n=getline(&line,&cap,stdin))>=0) {
  int blank=1; for(ssize_t i=0;i<n;i++) if(!isspace((unsigned char)line[i])) { blank=0; break; } if(blank) continue;
  if(n>INT32_MAX) fail("JSON line exceeds parser capacity");
  scalar_utf8((const unsigned char *)line,(size_t)n); scalar_escapes(line,(size_t)n);
  struct json_tokener *tok=json_tokener_new_ex(1024); json_tokener_set_flags(tok,JSON_TOKENER_STRICT|JSON_TOKENER_VALIDATE_UTF8);
  J *job=json_tokener_parse_ex(tok,line,(int)n); size_t end=json_tokener_get_parse_end(tok);
  if(json_tokener_get_error(tok)!=json_tokener_success) fail("invalid JSON");
  for(size_t i=end;i<(size_t)n;i++) if(!isspace((unsigned char)line[i])) fail("trailing JSON data");
  json_tokener_free(tok); J *out=run(job); puts(json_object_to_json_string_ext(out,JSON_C_TO_STRING_PLAIN)); json_object_put(out); json_object_put(job);
 }
 free(line); if(ferror(stdin)) fail("input read failure"); return 0;
}
