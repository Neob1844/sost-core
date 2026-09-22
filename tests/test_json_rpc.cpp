// Strict JSON reader tests — the layer that reads money must refuse anything it
// does not fully understand. Every case here is a way a node reply can be wrong:
// truncated mid-transfer, rejected by auth, hostile, or simply surprising.
#include "sost/json_rpc.h"
#include <cstdio>
#include <string>
using namespace sost::json;

static int g_pass=0,g_fail=0;
#define TEST(m,c) do{ if(c){++g_pass;} else {printf("  *** FAIL: %s [%d]\n",m,__LINE__);++g_fail;} }while(0)

static bool ok(const std::string& t){ Value v; return parse(t,v,nullptr); }
static bool bad(const std::string& t){ return !ok(t); }

int main(){
    printf("== accepts well-formed JSON ==\n");
    { Value v; TEST("object", parse("{\"a\":1}",v) && v.is_obj());
      int64_t i=0; TEST("int field", v.get_int("a",i) && i==1); }
    { Value v; TEST("array", parse("[1,2,3]",v) && v.is_arr() && v.a.size()==3); }
    { Value v; TEST("nested", parse("{\"a\":{\"b\":[{\"c\":true}]}}",v)); }
    { Value v; TEST("escapes", parse("{\"s\":\"a\\\"b\\\\c\\n\\u0041\"}",v));
      std::string s; v.get_str("s",s); TEST("escape value", s=="a\"b\\c\nA"); }
    { Value v; TEST("surrogate pair", parse("{\"s\":\"\\uD83D\\uDE00\"}",v));
      std::string s; v.get_str("s",s); TEST("emoji is 4 bytes", s.size()==4); }
    { Value v; TEST("negative + zero", parse("[-1,0,-0.5,1e3]",v)); }

    printf("== refuses malformed JSON ==\n");
    TEST("trailing content",   bad("{\"a\":1} garbage"));
    TEST("trailing comma",     bad("[1,2,]"));
    TEST("single quotes",      bad("{'a':1}"));
    TEST("unquoted key",       bad("{a:1}"));
    TEST("NaN",                bad("[NaN]"));
    TEST("Infinity",           bad("[Infinity]"));
    TEST("comment",            bad("{\"a\":1} // hi"));
    TEST("bare control char",  bad("{\"a\":\"x\ny\"}"));
    TEST("lone high surrogate",bad("{\"s\":\"\\uD83D\"}"));
    TEST("bad escape",         bad("{\"s\":\"\\q\"}"));
    TEST("leading zero",       bad("[01]"));
    TEST("empty input",        bad(""));
    TEST("duplicate key",      bad("{\"a\":1,\"a\":2}"));

    printf("== truncation: the shape a dropped connection makes ==\n");
    {
        const std::string full = "{\"result\":[{\"txid\":\"ab\",\"vout\":0,\"amount_stocks\":12345}]}";
        int refused=0;
        for (size_t n=1; n<full.size(); ++n) if (!ok(full.substr(0,n))) ++refused;
        TEST("every truncation refused", refused == (int)full.size()-1);
        TEST("the complete body parses", ok(full));
    }

    printf("== bounds ==\n");
    {
        std::string deep; for(int i=0;i<MAX_DEPTH+5;i++) deep += "[";
        for(int i=0;i<MAX_DEPTH+5;i++) deep += "]";
        TEST("depth limit enforced", bad(deep));
        std::string okdeep; for(int i=0;i<10;i++) okdeep+="["; okdeep+="1";
        for(int i=0;i<10;i++) okdeep+="]";
        TEST("reasonable depth fine", ok(okdeep));
    }
    {   // int64 edges: exact, or an error — never a silently lossy double
        Value v; TEST("int64 max", parse("[9223372036854775807]",v) && v.a[0].type==Value::T::Int
                                    && v.a[0].i==9223372036854775807LL);
        TEST("int64 overflow refused", bad("[9223372036854775808]"));
        Value w; TEST("real stays real", parse("[1.5]",w) && w.a[0].type==Value::T::Real);
        Value x; parse("[1.0]",x);
        TEST("1.0 is NOT an int", x.a[0].type==Value::T::Real);
    }

    printf("== scale: a real getaddressutxos reply ==\n");
    {
        std::string big = "{\"result\":[";
        const int N = 3000;
        for (int k=0;k<N;k++){
            if(k) big += ",";
            big += "{\"txid\":\"aabb\",\"vout\":" + std::to_string(k%4)
                 + ",\"amount_stocks\":392550432,\"height\":" + std::to_string(20000+k)
                 + ",\"coinbase\":true,\"mature\":" + (k%3?"true":"false")
                 + ",\"spendable\":" + (k%3?"true":"false") + ",\"output_type\":1}";
        }
        big += "]}";
        Value res; std::string err;
        TEST("3000-entry reply parses", rpc_result(big,res,&err));
        TEST("array of 3000", res.is_arr() && res.a.size()==(size_t)N);
        int64_t sum=0; int mature=0;
        for (const auto& u : res.a){ int64_t a=0; bool m=false;
            if (u.get_int("amount_stocks",a)) sum+=a;
            if (u.get_bool("mature",m) && m) ++mature; }
        TEST("amounts summed exactly", sum == (int64_t)N*392550432LL);
        TEST("maturity counted", mature == N - (N+2)/3);
    }

    printf("== JSON-RPC envelope: an error is NEVER an empty result ==\n");
    {
        Value r; std::string err;
        TEST("auth error surfaces", !rpc_result("{\"jsonrpc\":\"2.0\",\"id\":1,\"error\":{\"code\":-1,\"message\":\"unauthorized\"}}",r,&err));
        TEST("error message kept", err.find("unauthorized")!=std::string::npos);
        err.clear();
        TEST("missing result surfaces", !rpc_result("{\"jsonrpc\":\"2.0\",\"id\":1}",r,&err));
        TEST("distinct reason", err=="no_result_field");
        err.clear();
        TEST("null error is not an error", rpc_result("{\"error\":null,\"result\":[]}",r,&err));
        TEST("empty array is a real empty result", r.is_arr() && r.a.empty());
    }

    printf("== HTTP layer: 401 must not look like 'no funds' ==\n");
    {
        std::string body; std::string err;
        TEST("401 refused", !http_body("HTTP/1.1 401 Unauthorized\r\n\r\n{\"error\":\"x\"}",body,&err));
        TEST("code reported", err=="http_401");
        err.clear();
        TEST("200 passes", http_body("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"result\":1}",body,&err));
        TEST("body extracted", body=="{\"result\":1}");
        TEST("bare body accepted", http_body("{\"result\":1}",body,&err) && body=="{\"result\":1}");
        err.clear();
        TEST("500 refused", !http_body("HTTP/1.1 500 Internal Server Error\r\n\r\n",body,&err) && err=="http_500");
    }

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
