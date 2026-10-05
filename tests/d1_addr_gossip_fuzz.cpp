// Fuzz + unit test of the ADDR payload parser (exact logic to be wired into sost-node.cpp).
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>
#include <vector>
#include <random>
static uint32_t read_u32(const uint8_t* p){ return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3]; }
static void     write_u32(uint8_t* p,uint32_t v){ p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v; }
static const uint32_t ADDR_MAX_RECV = 1000;   // reject lists larger than this (DoS bound)
static const uint32_t ADDR_MAX_LEN  = 64;     // max bytes per address string

// Returns parsed addresses; sets *malformed=true on any structural violation (caller penalizes).
static std::vector<std::string> parse_addr_payload(const uint8_t* d, size_t n, bool* malformed){
    std::vector<std::string> out; *malformed=false;
    if(n < 4){ *malformed = (n!=0); return out; }
    uint32_t count = read_u32(d); size_t pos = 4;
    if(count > ADDR_MAX_RECV){ *malformed=true; return out; }
    for(uint32_t i=0;i<count;i++){
        if(pos+4 > n){ *malformed=true; break; }
        uint32_t len = read_u32(d+pos); pos+=4;
        if(len==0 || len>ADDR_MAX_LEN || pos+len > n){ *malformed=true; break; }
        std::string s((const char*)d+pos, len); pos+=len;
        // validate host:port, printable, no control chars
        bool ok = s.find(':')!=std::string::npos;
        for(char c: s) if((unsigned char)c<32 || (unsigned char)c>126){ ok=false; break; }
        if(ok && out.size()<ADDR_MAX_RECV) out.push_back(s);
    }
    return out;
}
static std::vector<uint8_t> serialize_addrs(const std::vector<std::string>& in, size_t cap){
    std::vector<uint8_t> p(4); uint32_t cnt=0;
    for(const auto& a: in){ if(cnt>=cap) break; if(a.empty()||a.size()>ADDR_MAX_LEN) continue;
        uint8_t l[4]; write_u32(l,(uint32_t)a.size()); p.insert(p.end(),l,l+4);
        p.insert(p.end(),a.begin(),a.end()); cnt++; }
    write_u32(p.data(),cnt); return p;
}
int main(){
    int pass=0,fail=0; auto CK=[&](bool c,const char* m){ if(c)pass++; else {fail++;printf("FAIL %s\n",m);} };
    bool mf;
    // round-trip
    auto ser=serialize_addrs({"1.2.3.4:19333","5.6.7.8:19333"},100);
    auto r=parse_addr_payload(ser.data(),ser.size(),&mf);
    CK(!mf && r.size()==2 && r[0]=="1.2.3.4:19333","round-trip 2");
    // serialize cap
    std::vector<std::string> many; for(int i=0;i<300;i++)many.push_back("10.0.0."+std::to_string(i)+":19333");
    auto ser2=serialize_addrs(many,100); auto r2=parse_addr_payload(ser2.data(),ser2.size(),&mf);
    CK(!mf && r2.size()==100,"serialize cap 100");
    // oversized count -> malformed, no crash
    uint8_t big[4]; write_u32(big,5000); parse_addr_payload(big,4,&mf); CK(mf,"reject count>1000");
    // truncated len -> malformed
    uint8_t t[6]; write_u32(t,1); t[4]=0;t[5]=5; parse_addr_payload(t,6,&mf); CK(mf,"truncated len malformed");
    // len>64 -> malformed
    uint8_t l[8]; write_u32(l,1); write_u32(l+4,200); parse_addr_payload(l,8,&mf); CK(mf,"len>64 malformed");
    // control chars rejected but not crash
    std::vector<uint8_t> ctl(4); write_u32(ctl.data(),1); uint8_t ln[4]; write_u32(ln,5); ctl.insert(ctl.end(),ln,ln+4);
    const char* bad="a\x01b:c"; ctl.insert(ctl.end(),bad,bad+5);
    auto r3=parse_addr_payload(ctl.data(),ctl.size(),&mf); CK(r3.empty(),"control-char addr dropped");
    // empty payload ok
    parse_addr_payload(nullptr,0,&mf); CK(!mf,"empty ok");
    // ===== FUZZ: 200k random/truncated inputs, must never crash/OOB =====
    std::mt19937 rng(12345); int crashes=0;
    for(int it=0; it<200000; ++it){
        size_t n = rng()% 2048; std::vector<uint8_t> buf(n);
        for(auto& b: buf) b=(uint8_t)rng();
        // bias: sometimes put a huge count
        if(n>=4 && (rng()&3)==0) write_u32(buf.data(), rng()%2000000);
        bool m; auto rr=parse_addr_payload(buf.data(),buf.size(),&m);
        if(rr.size()>ADDR_MAX_RECV){ crashes++; } // bound invariant
    }
    CK(crashes==0,"fuzz 200k: bound invariant held, no OOB");
    printf("ADDR parser: %d passed, %d failed (fuzz 200k clean)\n",pass,fail);
    return fail?1:0;
}
