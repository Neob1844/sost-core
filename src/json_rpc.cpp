// Strict JSON reader — see include/sost/json_rpc.h for the rationale.
#include "sost/json_rpc.h"

#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>

namespace sost::json {
namespace {

struct P {
    const char* p;
    const char* end;
    int depth{0};
    std::string err;

    bool fail(const char* m) { if (err.empty()) err = m; return false; }
    void ws() { while (p < end && (*p==' '||*p=='\t'||*p=='\n'||*p=='\r')) ++p; }
    bool eat(char c) { if (p < end && *p == c) { ++p; return true; } return false; }
    bool peek(char c) const { return p < end && *p == c; }

    bool value(Value& v);

    bool hex4(unsigned& cp) {
        if (end - p < 4) return fail("truncated \\u escape");
        cp = 0;
        for (int k = 0; k < 4; ++k) {
            char c = *p++;
            cp <<= 4;
            if (c >= '0' && c <= '9')      cp |= (unsigned)(c - '0');
            else if (c >= 'a' && c <= 'f') cp |= (unsigned)(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') cp |= (unsigned)(c - 'A' + 10);
            else return fail("bad \\u escape");
        }
        return true;
    }
    void utf8(unsigned cp, std::string& out) {
        if (cp < 0x80) out += (char)cp;
        else if (cp < 0x800) { out += (char)(0xC0|(cp>>6)); out += (char)(0x80|(cp&0x3F)); }
        else if (cp < 0x10000) { out += (char)(0xE0|(cp>>12)); out += (char)(0x80|((cp>>6)&0x3F)); out += (char)(0x80|(cp&0x3F)); }
        else { out += (char)(0xF0|(cp>>18)); out += (char)(0x80|((cp>>12)&0x3F)); out += (char)(0x80|((cp>>6)&0x3F)); out += (char)(0x80|(cp&0x3F)); }
    }

    bool string(std::string& out) {
        if (!eat('"')) return fail("expected string");
        out.clear();
        while (true) {
            if (p >= end) return fail("unterminated string");
            unsigned char c = (unsigned char)*p++;
            if (c == '"') return true;
            if (c < 0x20) return fail("raw control character in string");
            if (c != '\\') { out += (char)c; continue; }
            if (p >= end) return fail("unterminated escape");
            char e = *p++;
            switch (e) {
                case '"':  out += '"';  break;
                case '\\': out += '\\'; break;
                case '/':  out += '/';  break;
                case 'b':  out += '\b'; break;
                case 'f':  out += '\f'; break;
                case 'n':  out += '\n'; break;
                case 'r':  out += '\r'; break;
                case 't':  out += '\t'; break;
                case 'u': {
                    unsigned cp;
                    if (!hex4(cp)) return false;
                    if (cp >= 0xD800 && cp <= 0xDBFF) {          // surrogate pair
                        if (end - p < 2 || p[0] != '\\' || p[1] != 'u') return fail("lone high surrogate");
                        p += 2;
                        unsigned lo;
                        if (!hex4(lo)) return false;
                        if (lo < 0xDC00 || lo > 0xDFFF) return fail("bad low surrogate");
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                    } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                        return fail("lone low surrogate");
                    }
                    utf8(cp, out);
                    break;
                }
                default: return fail("bad escape");
            }
        }
    }

    bool number(Value& v) {
        const char* s = p;
        if (p < end && *p == '-') ++p;
        if (p >= end || !isdigit((unsigned char)*p)) return fail("bad number");
        if (*p == '0') { ++p; }
        else { while (p < end && isdigit((unsigned char)*p)) ++p; }
        bool integral = true;
        if (p < end && *p == '.') {
            integral = false; ++p;
            if (p >= end || !isdigit((unsigned char)*p)) return fail("bad fraction");
            while (p < end && isdigit((unsigned char)*p)) ++p;
        }
        if (p < end && (*p == 'e' || *p == 'E')) {
            integral = false; ++p;
            if (p < end && (*p == '+' || *p == '-')) ++p;
            if (p >= end || !isdigit((unsigned char)*p)) return fail("bad exponent");
            while (p < end && isdigit((unsigned char)*p)) ++p;
        }
        std::string tok(s, (size_t)(p - s));
        if (integral) {
            errno = 0;
            char* fin = nullptr;
            long long n = strtoll(tok.c_str(), &fin, 10);
            if (errno == ERANGE || !fin || *fin != '\0')
                return fail("integer out of int64 range");   // never silently a double
            v.type = Value::T::Int; v.i = (int64_t)n;
        } else {
            errno = 0;
            char* fin = nullptr;
            double d = strtod(tok.c_str(), &fin);
            if (!fin || *fin != '\0' || !std::isfinite(d)) return fail("bad real");
            v.type = Value::T::Real; v.d = d;
        }
        return true;
    }
};

bool P::value(Value& v) {
    if (++depth > MAX_DEPTH) return fail("nesting too deep");
    struct Pop { int& d; ~Pop(){ --d; } } pop{depth};
    ws();
    if (p >= end) return fail("unexpected end of input");
    char c = *p;
    if (c == '{') {
        ++p; v.type = Value::T::Obj; v.o.clear();
        ws();
        if (eat('}')) return true;
        while (true) {
            ws();
            std::string key;
            if (!string(key)) return false;
            ws();
            if (!eat(':')) return fail("expected ':'");
            Value child;
            if (!value(child)) return false;
            if (!v.o.emplace(key, std::move(child)).second) return fail("duplicate object key");
            ws();
            if (eat(',')) continue;
            if (eat('}')) return true;
            return fail("expected ',' or '}'");
        }
    }
    if (c == '[') {
        ++p; v.type = Value::T::Arr; v.a.clear();
        ws();
        if (eat(']')) return true;
        while (true) {
            Value child;
            if (!value(child)) return false;
            v.a.push_back(std::move(child));
            ws();
            if (eat(',')) continue;
            if (eat(']')) return true;
            return fail("expected ',' or ']'");
        }
    }
    if (c == '"') { v.type = Value::T::Str; return string(v.s); }
    if (c == 't') { if (end - p >= 4 && !memcmp(p,"true",4))  { p += 4; v.type=Value::T::Bool; v.b=true;  return true; } return fail("bad literal"); }
    if (c == 'f') { if (end - p >= 5 && !memcmp(p,"false",5)) { p += 5; v.type=Value::T::Bool; v.b=false; return true; } return fail("bad literal"); }
    if (c == 'n') { if (end - p >= 4 && !memcmp(p,"null",4))  { p += 4; v.type=Value::T::Null; return true; } return fail("bad literal"); }
    return number(v);
}

} // namespace

bool parse(const std::string& text, Value& out, std::string* err) {
    auto bail = [&](const char* m) { if (err) *err = m; return false; };
    if (text.size() > MAX_INPUT_SIZE) return bail("input too large");
    if (text.empty())                 return bail("empty input");
    P st{text.data(), text.data() + text.size()};
    Value v;
    if (!st.value(v)) { if (err) *err = st.err.empty() ? "parse error" : st.err; return false; }
    st.ws();
    if (st.p != st.end) return bail("trailing content after JSON value");
    out = std::move(v);
    return true;
}

bool http_body(const std::string& response, std::string& body_out, std::string* err) {
    auto bail = [&](const std::string& m) { if (err) *err = m; return false; };
    if (response.rfind("HTTP/", 0) == 0) {
        auto sp = response.find(' ');
        if (sp == std::string::npos || response.size() < sp + 4) return bail("malformed_http_status");
        std::string code = response.substr(sp + 1, 3);
        auto hdr_end = response.find("\r\n\r\n");
        body_out = (hdr_end == std::string::npos) ? std::string() : response.substr(hdr_end + 4);
        if (!(code.size() == 3 && code[0] == '2')) return bail("http_" + code);
        return true;
    }
    body_out = response;   // already a bare body
    return true;
}

bool rpc_result(const std::string& body, Value& result_out, std::string* err) {
    auto bail = [&](const std::string& m) { if (err) *err = m; return false; };
    Value doc;
    std::string perr;
    if (!parse(body, doc, &perr)) return bail("bad_json: " + perr);
    if (!doc.is_obj()) return bail("response is not a JSON object");
    if (const Value* e = doc.find("error")) {
        if (!e->is_null()) {
            std::string msg;
            if (e->is_obj()) { e->get_str("message", msg); }
            else if (e->type == Value::T::Str) msg = e->s;
            return bail("rpc_error: " + (msg.empty() ? std::string("(no message)") : msg));
        }
    }
    const Value* r = doc.find("result");
    if (!r) return bail("no_result_field");
    result_out = *r;
    return true;
}

} // namespace sost::json
