// Host-side unit tests for firmware/LalitStockFirmware/logic.h using the shared JSON vectors.
// Build: see firmware/test/run_host_tests.sh  (g++ -std=c++17 -I<ArduinoJson/src> ...)
// Owner: Lalit Nayyar <consult@lalit.cloud>. Not financial advice.
#include <ArduinoJson.h>

#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

#include "../LalitStockFirmware/logic.h"

static int failures = 0, checks = 0;
#define CHECK(cond, msg)                                                   \
  do {                                                                     \
    ++checks;                                                              \
    if (!(cond)) {                                                         \
      ++failures;                                                          \
      std::cerr << "FAIL: " << msg << "  (" #cond ")" << std::endl;        \
    }                                                                      \
  } while (0)

static std::string slurp(const std::string& path) {
  std::ifstream f(path, std::ios::binary);
  if (!f) {
    std::cerr << "cannot open " << path << std::endl;
    exit(2);
  }
  std::stringstream ss;
  ss << f.rdbuf();
  return ss.str();
}

static void testRefresh(const std::string& root) {
  JsonDocument doc;
  deserializeJson(doc, slurp(root + "/shared/test_vectors/refresh_cases.json"));
  for (JsonObject c : doc["cases"].as<JsonArray>()) {
    std::string name = c["name"].as<std::string>();
    ls::RefreshResult r = ls::computeRefresh(c["profile"].as<const char*>(), c["requested"].as<int>());
    CHECK(r.effective_s == c["effective"].as<int>(), name + " effective");
    CHECK(r.min_safe_s == c["min_safe"].as<int>(), name + " min_safe");
    CHECK(r.refresh_gap_s == c["refresh_gap"].as<int>(), name + " refresh_gap");
    CHECK(r.clamped == c["clamped"].as<bool>(), name + " clamped");
    CHECK(r.fallback == c["fallback"].as<bool>(), name + " fallback");
    char reason[220];
    ls::refreshReason(r, reason, sizeof reason);
    CHECK(strlen(reason) > 20, name + " reason");
  }
  // field ranges come from the generated contract header
  struct Range { const char* f; long mn, mx, df; } ranges[] = {
      {"page_duration_s", CFG_PAGE_DURATION_S_MIN, CFG_PAGE_DURATION_S_MAX, CFG_PAGE_DURATION_S_DEFAULT},
      {"fetch_interval_s", CFG_FETCH_INTERVAL_S_MIN, CFG_FETCH_INTERVAL_S_MAX, CFG_FETCH_INTERVAL_S_DEFAULT},
      {"rows_per_page", CFG_ROWS_PER_PAGE_MIN, CFG_ROWS_PER_PAGE_MAX, CFG_ROWS_PER_PAGE_DEFAULT},
      {"selected_page", CFG_SELECTED_PAGE_MIN, CFG_SELECTED_PAGE_MAX, CFG_SELECTED_PAGE_DEFAULT},
  };
  for (JsonObject c : doc["validation_cases"].as<JsonArray>()) {
    std::string name = c["name"].as<std::string>();
    const char* field = c["field"];
    Range* rg = nullptr;
    for (auto& r : ranges)
      if (strcmp(r.f, field) == 0) rg = &r;
    CHECK(rg != nullptr, name + " known field");
    if (!rg) continue;
    JsonVariant in = c["input"];
    ls::IntCheck res;
    if (in.is<const char*>()) res = ls::validateIntStr(in.as<const char*>(), rg->mn, rg->mx, rg->df);
    else if (in.is<long>() && !in.is<double>()) res = ls::validateInt(true, in.as<long>(), rg->mn, rg->mx, rg->df);
    else if (in.is<double>() && (double)(long)in.as<double>() == in.as<double>())
      res = ls::validateInt(true, (long)in.as<double>(), rg->mn, rg->mx, rg->df);
    else res = ls::validateInt(false, 0, rg->mn, rg->mx, rg->df);
    CHECK(res.value == c["result"].as<long>(), name + " value");
    CHECK(res.ok == c["ok"].as<bool>(), name + " ok");
  }
  CHECK(CFG_ROTATION_ENABLED_DEFAULT == true, "rotation default on");
  CHECK(CFG_PAGE_DURATION_S_DEFAULT == 10, "requested default 10 s");
  long v;
  CHECK(!ls::parseIntStrict("12abc", &v) && !ls::parseIntStrict("", &v) && !ls::parseIntStrict("-", &v), "strict parse");
  CHECK(ls::parseIntStrict("-5", &v) && v == -5, "negative parse");
}

static void testRotation(const std::string& root) {
  JsonDocument doc;
  deserializeJson(doc, slurp(root + "/shared/test_vectors/rotation_cases.json"));
  for (JsonObject sc : doc["scenarios"].as<JsonArray>()) {
    std::string name = sc["name"].as<std::string>();
    JsonObject in = sc["init"];
    ls::PageRotator rot;
    rot.init(in["page_count"].as<int>(), in["page"].as<int>(), in["enabled"].as<bool>(),
             in["effective_ms"].as<uint32_t>(), in["now"].as<uint32_t>());
    int i = 0;
    JsonArray steps = sc["steps"];
    for (JsonObject st : steps) {
      std::string op = st["op"].as<std::string>();
      uint32_t now = st["now"].as<uint32_t>();
      bool redraw = false, err = false;
      if (op == "tick") redraw = rot.tick(now);
      else if (op == "next") redraw = rot.next(now);
      else if (op == "goto") redraw = rot.gotoPage(st["arg"].as<long>(), now, &err);
      else if (op == "pause") rot.pause();
      else if (op == "resume") rot.resume(now);
      else if (op == "set_count") redraw = rot.setCount(st["arg"].as<int>(), now);
      else if (op == "data") redraw = rot.onData(st["arg"].as<bool>(), now);
      std::string where = name + " step " + std::to_string(i++) + " " + op;
      CHECK(rot.page == st["page"].as<int>(), where + " page");
      CHECK(redraw == st["redraw"].as<bool>(), where + " redraw");
      if (st["error"].is<bool>()) CHECK(err == st["error"].as<bool>(), where + " error");
    }
  }
  // millis() rollover: lastChange near UINT32_MAX, now wrapped around
  ls::PageRotator r;
  r.init(3, 1, true, 60000, 0xFFFFF000u);
  CHECK(!r.tick(0x00000100u), "rollover not yet");
  CHECK(r.tick(0x0000E000u) && r.page == 2, "rollover elapsed");
  ls::RefreshGate g;
  g.gapMs = 30000;
  CHECK(g.canRefresh(5), "gate open before first refresh");
  g.markStarted(1000);
  CHECK(!g.canRefresh(20000) && g.msUntilAllowed(20000) == 11000, "gate closed");
  CHECK(g.canRefresh(31000), "gate reopened");
}

static void testHeader(const std::string& root) {
  JsonDocument doc;
  deserializeJson(doc, slurp(root + "/shared/test_vectors/header_cases.json"));
  for (JsonObject a : doc["age_cases"].as<JsonArray>()) {
    char buf[16];
    ls::formatAge(a["age_s"].as<long>(), buf, sizeof buf);
    CHECK(std::string(buf) == a["text"].as<std::string>(), "age " + a["text"].as<std::string>());
  }
  int matched = 0;
  for (JsonObject c : doc["cases"].as<JsonArray>()) {
    std::string name = c["name"].as<std::string>();
    // Each case targets one panel; this binary checks the cases for the panel it was compiled for.
    std::string profile = c["profile"] | "JD79667_GDEY029F51H";
    if (profile != LS_PANEL_PROFILE) continue;
    ++matched;
    JsonObject s = c["status"];
    std::string dt = s["datetime"].isNull() ? "" : s["datetime"].as<std::string>();
    std::string lo = s["last_ok"].isNull() ? "" : s["last_ok"].as<std::string>();
    ls::HeaderStatus hs{s["datetime"].isNull() ? nullptr : dt.c_str(), s["last_ok"].isNull() ? nullptr : lo.c_str(),
                        s["wifi"].as<bool>(), s["api"].as<const char*>(), s["market"].as<const char*>(),
                        s["flag"].as<const char*>(), s["page"].as<int>(), s["pages"].as<int>(),
                        s["age_s"].isNull() ? -1L : s["age_s"].as<long>(), s["offline"].as<bool>()};
    ls::DrawOp ops[24];
    int n = ls::buildHeaderFooterOps(hs, ops, 24);
    JsonArray exp = c["ops"];
    CHECK(n == (int)exp.size(), name + " op count " + std::to_string(n) + " vs " + std::to_string(exp.size()));
    for (int i = 0; i < n && i < (int)exp.size(); i++) {
      JsonArray e = exp[i];
      std::string kind = e[0].as<std::string>();
      const ls::DrawOp& o = ops[i];
      std::string where = name + " op " + std::to_string(i);
      CHECK(o.kind == kind[0], where + " kind");
      CHECK(o.x == e[1].as<int>() && o.y == e[2].as<int>(), where + " xy");
      if (kind == "T") {
        CHECK(o.size == e[3].as<int>() && o.color == e[4].as<std::string>()[0], where + " size/color");
        CHECK(std::string(o.text) == e[5].as<std::string>(), where + " text '" + o.text + "'");
      } else if (kind == "H") {
        CHECK(o.w == e[3].as<int>() && o.color == e[4].as<std::string>()[0], where + " line");
      } else {
        CHECK(o.w == e[3].as<int>() && o.h == e[4].as<int>() && o.color == e[5].as<std::string>()[0], where + " rect");
      }
    }
  }
  CHECK(matched > 0, std::string("header vectors exist for ") + LS_PANEL_PROFILE);
}

static void testFixture(const std::string& root) {
  // The firmware must accept the shared fixture for its panel within its documented limits.
  std::string file = std::string(L_ID) == "168x384" ? "dashboard_3page.json"
                                                     : std::string("dashboard_3page_") + LS_PANEL_BUILD + ".json";
  std::string raw = slurp(root + "/shared/fixtures/" + file);
  CHECK((int)raw.size() <= L_LIM_MAX_RESPONSE_BYTES, "fixture within response limit");
  JsonDocument doc;
  CHECK(deserializeJson(doc, raw) == DeserializationError::Ok, "fixture parses");
  CHECK(std::string(doc["layout"] | "") == L_ID, "fixture layout matches the compiled panel");
  JsonArray pages = doc["pages"];
  CHECK(pages.size() == 3, "fixture has 3 pages");
  const char* pal = L_PALETTE;
  for (JsonObject p : pages) {
    JsonArray pageOps = p["ops"];
    for (JsonArray op : pageOps) {
      const char* col = op[0] == "H" ? op[4] | "?" : op[0] == "T" ? op[4] | "?" : op[5] | "?";
      CHECK(strchr(pal, col[0]) != nullptr, std::string("fixture colour ") + col + " in palette " + pal);
      int x = op[1], y = op[2];
      CHECK(x >= 0 && x < L_WIDTH && y >= L_BODY_TOP && y < L_BODY_BOTTOM + 1, "fixture op inside body");
    }
  }
  for (JsonObject p : pages) CHECK(p["ops"].as<JsonArray>().size() <= L_LIM_MAX_OPS_PER_PAGE, "ops per page");
}

int main(int argc, char** argv) {
  std::string root = argc > 1 ? argv[1] : "../..";
  testRefresh(root);
  testRotation(root);
  testHeader(root);
  testFixture(root);
  std::cout << "[" << LS_PANEL_BUILD << " " << L_ID << " " << L_PALETTE << "] " << checks - failures << "/" << checks
            << " checks passed" << std::endl;
  return failures ? 1 : 0;
}
