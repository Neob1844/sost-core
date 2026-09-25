#include <vector>
#include <string>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
static int b64_value(char c){ if(c>='A'&&c<='Z')return c-'A'; if(c>='a'&&c<='z')return c-'a'+26;
  if(c>='0'&&c<='9')return c-'0'+52; if(c=='+')return 62; if(c=='/')return 63; return -1; }
// OLD (int val — UB) compilado normal para observar el comportamiento x86 actual
static bool dec_old(const std::string& b64, std::vector<uint8_t>& out){ out.clear(); out.reserve(b64.size()*3/4);
  int val=0,bits=0; for(char c:b64){ if(c=='=')break; if(c==' '||c=='\n'||c=='\r'||c=='\t')continue;
    int v=b64_value(c); if(v<0)return false; val=(val<<6)|v; bits+=6; if(bits>=8){bits-=8; out.push_back((uint8_t)((val>>bits)&0xFF));}} return true; }
// NEW (uint32_t val)
static bool dec_new(const std::string& b64, std::vector<uint8_t>& out){ out.clear(); out.reserve(b64.size()*3/4);
  uint32_t val=0; int bits=0; for(char c:b64){ if(c=='=')break; if(c==' '||c=='\n'||c=='\r'||c=='\t')continue;
    int v=b64_value(c); if(v<0)return false; val=(val<<6)|v; bits+=6; if(bits>=8){bits-=8; out.push_back((uint8_t)((val>>bits)&0xFF));}} return true; }
static unsigned long seed=0x1234;
static unsigned r(){ seed=seed*6364136223846793005ULL+1; return (unsigned)(seed>>33); }
int main(){
  const char* B="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  long mism=0, tot=0;
  // casos fijos: validos, invalidos, truncados, con '=' y espacios
  const char* fixed[]={"", "QQ==","QUJD","aGVsbG8gd29ybGQ=","####","AB CD\nEF","====","A","AB","ABC","ABCD",
    "not_base64!!","zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz","++++////","AAAA=AAA"};
  for(auto f:fixed){ std::vector<uint8_t>a,b; bool ra=dec_old(f,a),rb=dec_new(f,b); tot++;
    if(ra!=rb||a!=b){mism++; printf("  MISMATCH fixed '%s'\n",f);} }
  // aleatorios + extremadamente largos
  for(int it=0; it<200000; it++){ int len=(it%50==0)?(1000+ (int)(r()%200000)):(int)(r()%256); // huge cada 50
    std::string s; s.reserve(len); for(int i=0;i<len;i++){ unsigned x=r()%70; s.push_back(x<64?B[x]:(char)("= \n\t!#"[x-64])); }
    std::vector<uint8_t>a,b; bool ra=dec_old(s,a),rb=dec_new(s,b); tot++;
    if(ra!=rb||a!=b){ mism++; if(mism<=3) printf("  MISMATCH random len=%d\n",len);} }
  printf("total=%ld  mismatches=%ld  -> %s\n", tot, mism, mism==0?"BEHAVIOR-IDENTICAL":"DIVERGE");
  return mism==0?0:1;
}
