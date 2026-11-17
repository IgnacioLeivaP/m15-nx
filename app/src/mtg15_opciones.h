// The options the game's own Settings menu sets (2026-11-08): the language and the button icons (Xbox, PlayStation,
// Nintendo Switch). Our version of the menu (lua/menus.help_options.settings.basic.lua, mtg15_lua_scripts.cpp) sends
// them as game:playMovie("mtg15:<key>=<value>"), which mtg15_movies.cpp hands to HandleMessage instead of playing a
// video. They are kept in mtg15_opciones.txt next to the executable (key=value lines).
//   idioma  en es fr de it ja: the game's language from the next start (mtg15_app.h; mtg15_language in the config, or
//           a command-line option, wins over it)
//   estilo  xbox ps switch: the button icons

#pragma once

#include <string>

namespace mtg15::opciones {

// The saved value of `key`, or "" when there is none.
std::string Get(const std::string& key);

// A message from the menu ("mtg15:idioma=es"): saves it and returns true; false for anything else (a real movie).
bool HandleMessage(const std::string& message);

// The game's current language (from the SDK's user_language): en, ja, de, fr, es, it or pt.
std::string CurrentLanguage();

// The button icon style in use: xbox, ps or switch.
std::string ButtonStyle();

}  // namespace mtg15::opciones
