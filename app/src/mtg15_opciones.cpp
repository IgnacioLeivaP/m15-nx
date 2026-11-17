// See mtg15_opciones.h.

#include "mtg15_opciones.h"

#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/logging.h>

REXCVAR_DECLARE(uint32_t, user_language);  // the SDK's (xam_user.cpp)

namespace mtg15::opciones {
namespace {

std::mutex g_mutex;
bool g_read = false;
std::map<std::string, std::string> g_values;

std::filesystem::path File() { return rex::filesystem::GetExecutableFolder() / "mtg15_opciones.txt"; }

void ReadLocked() {
  if (g_read) return;
  g_read = true;
  std::ifstream in(File());
  std::string line;
  while (std::getline(in, line)) {
    while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
    const size_t eq = line.find('=');
    if (line.empty() || line[0] == '#' || eq == std::string::npos) continue;
    g_values[line.substr(0, eq)] = line.substr(eq + 1);
  }
}

void WriteLocked() {
  std::ofstream out(File(), std::ios::trunc);
  out << "# Opciones del menu Configuracion de Magic 2013 (idioma: al reiniciar el juego)\n";
  for (const auto& [key, value] : g_values) out << key << '=' << value << '\n';
}

bool Allowed(const std::string& key, const std::string& value) {
  if (key == "idioma") return value == "en" || value == "es" || value == "fr" || value == "de" || value == "it" ||
                              value == "ja" || value == "pt" || value == "ko" || value == "ru";
  if (key == "estilo") return value == "xbox" || value == "ps" || value == "switch";
  return false;
}

}  // namespace

std::string Get(const std::string& key) {
  std::lock_guard<std::mutex> lock(g_mutex);
  ReadLocked();
  auto it = g_values.find(key);
  return it == g_values.end() ? std::string() : it->second;
}

bool HandleMessage(const std::string& message) {
  static const std::string kPrefix = "mtg15:";
  if (message.compare(0, kPrefix.size(), kPrefix) != 0) return false;
  const std::string body = message.substr(kPrefix.size());
  const size_t eq = body.find('=');
  const std::string key = body.substr(0, eq), value = eq == std::string::npos ? "" : body.substr(eq + 1);
  if (!Allowed(key, value)) {
    REXLOG_WARN("[opciones] unknown message '{}'", message);
    return true;
  }
  std::lock_guard<std::mutex> lock(g_mutex);
  ReadLocked();
  g_values[key] = value;
  WriteLocked();
  REXLOG_INFO("[opciones] {} = {} (saved in {})", key, value, File().string());
  return true;
}

std::string CurrentLanguage() {
  switch (REXCVAR_GET(user_language)) {
    case 2: return "ja";
    case 3: return "de";
    case 4: return "fr";
    case 5: return "es";
    case 6: return "it";
    case 9: return "pt";
    case 7: return "ko";
    case 11: return "ru";
    default: return "en";
  }
}

std::string ButtonStyle() {
  const std::string style = Get("estilo");
  return style.empty() ? "xbox" : style;
}

}  // namespace mtg15::opciones
