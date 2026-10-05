// Isolated unit test of the D1 peer-store logic (same code path as sost-node.cpp).
#include <string>
#include <vector>
#include <algorithm>
#include <cstdio>
#include <sys/stat.h>
static const size_t PEER_STORE_MAX = 256;
static std::string peer_store_path(const std::string& chain_path){
    std::string dir="."; if(!chain_path.empty()){ auto p=chain_path.find_last_of('/');
        dir=(p==std::string::npos)?std::string("."):chain_path.substr(0,p); if(dir.empty())dir="/"; }
    return dir+"/peers.txt";
}
static void save_set(const std::string& path, const std::vector<std::string>& in){
    std::vector<std::string> addrs;
    for(const auto& a:in){ if(!a.empty() && std::find(addrs.begin(),addrs.end(),a)==addrs.end()){ addrs.push_back(a); if(addrs.size()>=PEER_STORE_MAX)break; } }
    if(addrs.empty())return;
    std::string tmp=path+".tmp"; FILE* fp=fopen(tmp.c_str(),"w"); if(!fp)return;
    for(const auto& a:addrs)fprintf(fp,"%s\n",a.c_str()); fflush(fp); fclose(fp); chmod(tmp.c_str(),0600); rename(tmp.c_str(),path.c_str());
}
static std::vector<std::string> load(const std::string& path){
    std::vector<std::string> out; FILE* fp=fopen(path.c_str(),"r"); if(!fp)return out; char line[256];
    while(fgets(line,sizeof(line),fp)&&out.size()<PEER_STORE_MAX){ std::string ln(line);
        while(!ln.empty()&&(ln.back()=='\n'||ln.back()=='\r'||ln.back()==' '))ln.pop_back();
        if(ln.empty()||ln.find(':')==std::string::npos)continue;
        bool ok=true; for(char c:ln)if((unsigned char)c<32){ok=false;break;} if(ok)out.push_back(ln); }
    fclose(fp); return out;
}
int main(){
    int pass=0,fail=0; auto CK=[&](bool c,const char* m){ if(c){pass++;} else {fail++;printf("FAIL: %s\n",m);} };
    std::string p="/tmp/d1_peers_test.txt"; remove(p.c_str());
    // path derivation
    CK(peer_store_path("/opt/sost/chain.json")=="/opt/sost/peers.txt","path from chain.json");
    CK(peer_store_path("")=="./peers.txt","path fallback .");
    // round-trip + dedupe
    save_set(p, {"1.2.3.4:19333","5.6.7.8:19333","1.2.3.4:19333"});
    auto r=load(p); CK(r.size()==2,"dedupe to 2"); CK(r[0]=="1.2.3.4:19333"&&r[1]=="5.6.7.8:19333","round-trip order");
    // mode 600
    struct stat st; stat(p.c_str(),&st); CK((st.st_mode&0777)==0600,"mode 600");
    // validation: reject no-colon + control chars + empty
    FILE* f=fopen(p.c_str(),"w"); fprintf(f,"goodhost:19333\nnocolonhost\n\nbad\x01host:1\n9.9.9.9:19333\n"); fclose(f);
    auto r2=load(p); CK(r2.size()==2,"reject garbage (keep 2 valid)"); CK(r2[0]=="goodhost:19333"&&r2[1]=="9.9.9.9:19333","valid kept");
    // cap: write 300, load <=256
    f=fopen(p.c_str(),"w"); for(int i=0;i<300;i++)fprintf(f,"10.0.%d.%d:19333\n",i/256,i%256); fclose(f);
    CK(load(p).size()<=PEER_STORE_MAX,"bounded <=256");
    // empty set never wipes
    save_set(p,{}); CK(load(p).size()>0,"empty save does not wipe");
    remove(p.c_str()); remove((p+".tmp").c_str());
    printf("D1 peer-store unit: %d passed, %d failed\n",pass,fail);
    return fail?1:0;
}
