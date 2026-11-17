// Legacy menu-message compatibility. The installer selects the language at build time.
// Controller glyphs are always Nintendo Switch; there is no style selector.

#pragma once

#include <string>

namespace mtg15::opciones {

// The saved value of `key`, or "" when there is none.
std::string Get(const std::string& key);

// A message from the menu ("mtg15:idioma=es"): saves it and returns true; false for anything else (a real movie).
bool HandleMessage(const std::string& message);

// The game's current language (from the SDK's user_language): en, ja, de, fr, es, it or pt.
std::string CurrentLanguage();

// Always "switch" for this Switch-specific port.
std::string ButtonStyle();

}  // namespace mtg15::opciones
