#!/usr/bin/env python3
"""Installer for the Nintendo Switch port of a Magic: The Gathering - Duels of the Planeswalkers game.

You bring your own, legally bought game files; this script checks them, generates everything that is made from them
(the recompiled game code, the shaders, the button icons, the patched menu script, the data pack) and builds the folder
you copy to the SD card.

    python install/install.py --game mtg15 --xex default.xex --xexp default.xexp --data <game folder> /
        --dlc <folder with the DLC packages> --out <output folder>

Nothing of the game is part of this repository: the files are checked against the SHA-256 table of every game
(install/games/<id>.json), copied to a staging folder outside the repository, and only read from there afterwards.

    --dry-run          print the steps and their commands, run nothing
    --only a,b         run only these steps        --skip a,b     run everything but these
    --stage DIR        staging folder (default: <out>/stage)
    --jobs N           parallel compile jobs for the NRO
    --list-steps       the step names and what each one does

Python 3.8+ (standard library), plus Pillow and numpy for the button icons and CMake, Ninja, devkitPro and LLVM clang
for the builds; the tool check at the start says what is missing and how to install it.
"""
import argparse
import re
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GAMES = os.path.join(HERE, "games")

STEP_HELP = [
    ("verify", "check the SHA-256 of the game files you give it"),
    ("stage", "copy the game files to the staging folder and mount them for the build"),
    ("icons", "generate Switch texture overrides from your own converted texture dumps"),
    ("lua", "generate the three current Lua wrappers from your own runtime dumps"),
    ("pack", "pack the game folder into game_root.nxpack + game_root.nxidx"),
    ("codegen", "build the ReXGlue code generator and translate default.xex to C++"),
    ("shaders", "make deko3d_glsl.bin and Renut's shader cache from the game's shaders"),
    ("nro", "compile mtg15.nro for the Switch"),
    ("assemble", "build the SD card folder and print what to copy"),
]


STEP_TOOLS = {
    'verify': (), 'stage': (), 'lua': (), 'pack': (), 'assemble': (),
    'icons': ('pillow',),
    'codegen': ('cmake', 'ninja', 'clang'),
    'shaders': ('cmake', 'ninja', 'clang', 'bash'),
    'nro': ('cmake', 'ninja', 'devkitpro'),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n = n / 1024.0


def which(name):
    return shutil.which(name)


class Installer:
    def __init__(self, args):
        self.args = args
        self.dry = args.dry_run
        self.repo = REPO
        self.sdk = os.path.abspath(args.sdk or os.path.join(REPO, "sdk"))
        self.root = os.path.abspath(args.stage or os.path.join(args.out, "stage"))
        for destination in (self.root, os.path.abspath(args.out)):
            try:
                inside_repo = os.path.commonpath([destination, REPO]) == REPO
            except ValueError:  # different Windows drives
                inside_repo = False
            if inside_repo:
                raise ValueError("--out and --stage must be outside this repository")
        with open(os.path.join(GAMES, args.game + ".json"), encoding="utf-8") as fh:
            self.game = json.load(fh)
        self.out = os.path.abspath(args.out)
        self.stage_dir = self.root
        self.gamedata = os.path.join(self.stage_dir, "assets", "game_root")
        self.sd = os.path.join(self.out, "switch", self.game["sdcard_folder"])
        self.missing = {}

    # --- plumbing ------------------------------------------------------------------------------------------------
    def say(self, msg):
        print(msg)

    def step(self, msg):
        print("")
        print("== " + msg)

    def run(self, cmd, cwd=None, env=None, what=None):
        printable = " ".join(cmd)
        if what:
            self.say("   " + what)
        self.say("   > " + printable)
        if self.dry:
            return 0
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        full_env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", str(self.args.jobs))
        proc = subprocess.run(cmd, cwd=cwd or self.root, env=full_env)
        if proc.returncode != 0:
            sys.exit("command failed (exit %d): %s" % (proc.returncode, printable))
        return proc.returncode

    def path(self, key):
        return os.path.join(self.root, self.game["sources"][key])

    def ask_missing(self, needed):
        missing = [self.missing[k] for k in needed if k in self.missing]
        if not missing:
            return
        print('')
        print('These tools are missing:')
        for line in missing:
            print('  - ' + line)
        print('')
        print('Install them and run this again. Each step only needs the tools it uses, so --only')
        print('verify works without them, and --dry-run prints every command without running it.')
        if not self.dry:
            sys.exit(2)

    # --- 1. verify -------------------------------------------------------------------------------------------
    def find_one(self, name, where):
        for folder in where:
            if not folder:
                continue
            candidate = os.path.join(folder, name)
            if os.path.isfile(candidate):
                return candidate
        return None

    def check_file(self, path, spec, label):
        if path is None:
            return None, "%s: not found" % label
        if not os.path.isfile(path):
            return None, "%s: %s does not exist" % (label, path)
        size = os.path.getsize(path)
        if size != spec["size"]:
            return path, chr(10).join([
                "%s: %s is %d bytes, expected %d" % (label, os.path.basename(path), size, spec["size"]),
                "     That is not the file this port was made from: check you picked the right one, or that",
                "     the copy finished."])
        digest = sha256(path)
        if digest != spec["sha256"]:
            return path, chr(10).join([
                "%s: %s has SHA-256 %s, expected %s" % (label, os.path.basename(path), digest, spec["sha256"]),
                "     A patched or modified copy will not work: use the untouched file."])
        self.say("   ok  %-22s %10s  %s" % (os.path.basename(path), human(size), digest[:16] + "..."))
        return path, None

    def do_verify(self):
        self.step("verify the game files")
        problems = []
        a = self.args
        data_dir = os.path.abspath(a.data) if a.data else None
        if data_dir and not os.path.isdir(data_dir):
            sys.exit("--data is not a folder: %s" % data_dir)
        tu_dirs = [os.path.abspath(a.tu) if a.tu else None,
                   os.path.dirname(os.path.abspath(a.xexp)) if a.xexp else None,
                   data_dir]
        xex = os.path.abspath(a.xex) if a.xex else self.find_one(self.game["requires"]["xex"]["name"], [data_dir])
        xexp = os.path.abspath(a.xexp) if a.xexp else None
        if xexp is None:
            problems.append("default.xexp: pass it with --xexp (it comes from the Title Update package)")
        self.xex, err = self.check_file(xex, self.game["requires"]["xex"], "default.xex")
        if err:
            problems.append(err)
        self.xexp, err = self.check_file(xexp, self.game["requires"]["xexp"], "default.xexp (Title Update 0.0.6.2)")
        if err:
            problems.append(err)
        self.data_files = {}
        for spec in self.game["data_files"]:
            found = self.find_one(spec["name"], [data_dir] + tu_dirs)
            path, err = self.check_file(found, spec, spec["name"])
            if err:
                problems.append(err)
            else:
                self.data_files[spec["name"]] = path
        self.dlc = []
        if a.dlc:
            dlc_dir = os.path.abspath(a.dlc)
            if not os.path.isdir(dlc_dir):
                sys.exit("--dlc is not a folder: %s" % dlc_dir)
            by_hash = {}
            for base, _, files in os.walk(dlc_dir):
                for name in files:
                    p = os.path.join(base, name)
                    if self.dry:
                        by_hash[name] = p
                        continue
                    if os.path.getsize(p) in [d["size"] for d in self.game["dlc_packages"]]:
                        by_hash[sha256(p)] = p
            for spec in self.game["dlc_packages"]:
                p = None
                if self.dry:
                    p = by_hash.get(spec["package"])
                else:
                    p = by_hash.get(spec["sha256"])
                if p is None:
                    problems.append("DLC %d (%s): no package with SHA-256 %s under %s"
                                    % (spec["id"], spec["label"], spec["sha256"][:16] + "...", dlc_dir))
                    continue
                self.say("   ok  %-22s %10s  %s" % ("DLC %d %s" % (spec["id"], spec["label"]), human(spec["size"]),
                                                   spec["sha256"][:16] + "..."))
                self.dlc.append((spec, p))
        else:
            self.say("   (no --dlc: the folder will have no downloadable content)")
        if problems:
            print("")
            print("The game files do not match:")
            for p in problems:
                print("  * " + p)
            sys.exit(3)
        self.verify_captures()
        self.say("   all files match")
        return True

    # --- 2. stage ------------------------------------------------------------------------------------------------
    def do_stage(self):
        self.step("stage the game files in " + self.stage_dir)
        data_dir = os.path.abspath(self.args.data) if self.args.data else None
        self.say("   game data:  " + self.gamedata)
        if self.dry:
            self.say("   (would copy the game folder and the verified files there)")
            return
        os.makedirs(self.gamedata, exist_ok=True)
        for folder in ("app", "tools"):
            source = os.path.join(self.repo, folder)
            target = os.path.join(self.root, folder)
            if os.path.exists(target):
                raise ValueError("Work tree exists; choose a new --stage directory: " + target)
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        dependencies = self.args.thirdparty
        if not dependencies or not os.path.isdir(dependencies):
            raise ValueError("--thirdparty must contain plume, uam, imgui and reblue-XenosRecomp")
        for folder in ("plume", "uam", "imgui", "reblue-XenosRecomp"):
            if not os.path.isdir(os.path.join(dependencies, folder)):
                raise ValueError("Missing --thirdparty dependency: " + folder)
        dxc = os.path.join(dependencies, "reblue-XenosRecomp", "thirdparty", "dxc-bin", "bin", "x64", "dxc.exe")
        if os.name == "nt" and not os.path.isfile(dxc):
            raise ValueError("--thirdparty is missing XenosRecomp's DXC package: " + dxc)
        shutil.copytree(dependencies, os.path.join(self.root, "app", "thirdparty"))
        if self.args.icon:
            from PIL import Image
            os.makedirs(os.path.join(self.root, "out"), exist_ok=True)
            with Image.open(self.args.icon) as icon:
                icon.convert("RGB").resize((256, 256)).save(os.path.join(self.root, "out", "icon.jpg"))
        if data_dir:
            for name in self.game.get("optional_data", []):
                source = os.path.join(data_dir, name)
                if os.path.isdir(source):
                    shutil.copytree(source, os.path.join(self.gamedata, name))
                elif os.path.isfile(source):
                    shutil.copy2(source, os.path.join(self.gamedata, name))
        shutil.copy2(self.xex, os.path.join(self.gamedata, self.game["requires"]["xex"]["name"]))
        shutil.copy2(self.xexp, os.path.join(self.gamedata, self.game["requires"]["xexp"]["name"]))
        for name, path in self.data_files.items():
            dst = os.path.join(self.gamedata, name)
            if os.path.abspath(path) != os.path.abspath(dst):
                shutil.copy2(path, dst)
        # The manifest reads this work tree directly; the repository is never mounted or modified.

    # --- 3. icons ------------------------------------------------------------------------------------------------
    def verify_captures(self):
        self.capture_inputs = {}
        for category, argument in (("lua", self.args.lua_dump), ("shader", self.args.shader_dump), ("texture", self.args.texture_dump)):
            inputs = {}
            if argument:
                for entry in self.game[category + "_captures"]:
                    name = entry.get("name", entry.get("file"))
                    path = os.path.join(os.path.abspath(argument), name)
                    if not os.path.isfile(path):
                        raise ValueError("Missing " + category + " capture: " + name)
                    with open(path, "rb") as stream: data = stream.read()
                    if category == "lua":
                        sys.path.insert(0, os.path.join(self.repo, "install"))
                        import menus
                        data = menus.normalize(data)
                    if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                        raise ValueError("Capture does not match this build: " + name)
                    inputs[name] = path
                self.say("   verified %d %s captures" % (len(inputs), category))
            self.capture_inputs[category] = inputs


    def do_icons(self):
        self.step("Switch button textures from your own converted texture captures")
        if not self.args.texture_dump:
            raise ValueError("--texture-dump is required for Switch button icons")
        self.run([sys.executable, os.path.join(self.root, "tools", "iconos15.py"),
                  "--source", os.path.abspath(self.args.texture_dump),
                  "--out", os.path.join(self.root, "out", "mtg15_texturas.bin")])


    def do_lua(self):
        self.step("menu wrappers from your own decrypted Lua captures")
        if not self.args.lua_dump:
            raise ValueError("--lua-dump is required: encrypted ZED archives cannot be patched offline")
        if self.dry:
            self.say("   would generate the three current menu wrappers")
            return
        sys.path.insert(0, os.path.join(self.repo, "install"))
        import menus
        destination = os.path.join(self.sd, "lua")
        os.makedirs(destination, exist_ok=True)
        for entry in self.game["lua_captures"]:
            name = entry["module"]
            with open(self.capture_inputs["lua"][entry["file"]], "rb") as stream:
                output = menus.build(name, stream.read())
            with open(os.path.join(destination, name + ".lua"), "wb") as stream: stream.write(output)
            self.say("   generated " + name)


    def do_pack(self):
        self.step("data pack (game_root.nxpack + .nxidx)")
        out_dir = self.path("asset_pack_dir")
        self.run([sys.executable, os.path.join(self.root, "tools", "build_asset_pack.py"), self.gamedata,
                  "--out-dir", out_dir, "--verify"],
                 what="one file the console keeps open instead of thousands of small ones")
        if not self.dry:
            os.makedirs(self.sd, exist_ok=True)
            base = os.path.join(out_dir, os.path.basename(self.gamedata))
            for ext in (".nxpack", ".nxidx"):
                shutil.copy2(base + ext, os.path.join(self.sd, "game_root" + ext))

    # --- 6. codegen ----------------------------------------------------------------------------------------------
    def do_codegen(self):
        self.step("recompiled game code (ReXGlue code generator)")
        needed = ("FFmpeg", "sdl3", "glslang", "fmt", "tomlplusplus", "spirv-tools")
        missing = [name for name in needed if not os.path.isdir(os.path.join(self.sdk, "thirdparty", name))]
        if missing and not self.dry and not self.args.rexglue:
            sys.exit("SDK dependencies missing: " + ", ".join(missing) +
                     ". Run tools/fetch_thirdparty.py before installing.")
        host = self.path("host_build_dir")
        py = sys.executable
        cmd = [self.cmake, "-S", self.sdk, "-B", host, "-G", "Ninja",
               "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_COMPILER=" + self.clang,
               "-DCMAKE_CXX_COMPILER=" + self.clang_pp,
               "-DCMAKE_C_FLAGS=-march=x86-64-v2", "-DCMAKE_CXX_FLAGS=-march=x86-64-v2",
               "-DCMAKE_MAKE_PROGRAM=" + self.ninja, "-DPython3_EXECUTABLE=" + py, "-DPYTHON_EXECUTABLE=" + py,
               "-DREXGLUE_OUTPUT_ROOT=" + os.path.join(self.root, "out", "sdk")]
        if self.args.rexglue:
            rexglue = os.path.abspath(self.args.rexglue)
        else:
            self.run(cmd, what="configure the code generator (host build)")
            self.run([self.cmake, "--build", host, "--target", "rexglue", "-j", str(self.args.jobs)], what="build rexglue")
            rexglue = self.find_rexglue(os.path.join(self.root, "out", "sdk"))
        app = os.path.join(self.root, "app")
        env = {"REX_MAX_JUMP_TABLE_ENTRIES": "4096",
               "REXGLUE_DUMP_IMAGE": os.path.join(self.root, "out", "default_image.bin")}
        self.run([rexglue, "codegen", os.path.basename(self.game["sources"]["manifest"])], cwd=app, env=env,
                 what="default.xex -> C++ (app/generated)")
        if not self.dry:
            with open(os.path.join(self.path("generated_dir"), "codegen_profile.txt"), "w") as fh:
                fh.write("optimised")
        self.rexglue = rexglue

    def find_rexglue(self, host):
        best = None
        for base, _, files in os.walk(host):
            for name in files:
                if name in ("rexglue.exe", "rexglue", "rexgluerd.exe", "rexgluerd"):
                    p = os.path.join(base, name)
                    if best is None or os.path.getmtime(p) > os.path.getmtime(best):
                        best = p
        if best is None and not self.dry:
            sys.exit("the code generator was not built (no rexglue under %s)" % host)
        return best or os.path.join(host, "rexglue")

    # --- 7. shaders ----------------------------------------------------------------------------------------------
    def do_shaders(self):
        self.step("translate the user's captured shader containers")
        if not self.args.shader_dump:
            raise ValueError("--shader-dump is required for encrypted ZED game shaders")
        py = sys.executable
        dump = self.path("renut_dump")
        if not self.dry:
            os.makedirs(dump, exist_ok=True)
            for name, path in self.capture_inputs["shader"].items(): shutil.copy2(path, os.path.join(dump, name))
        pc = self.path("pc_build_dir")
        xenos = self.args.xenos_recomp
        if not xenos:
            self.run([self.cmake, "-S", os.path.join(self.root, "app"), "-B", pc, "-G", "Ninja",
                      "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_COMPILER=" + self.clang,
                      "-DCMAKE_CXX_COMPILER=" + self.clang_pp,
                      "-DCMAKE_C_FLAGS=-march=x86-64-v2", "-DCMAKE_CXX_FLAGS=-march=x86-64-v2",
                      "-DCMAKE_MAKE_PROGRAM=" + self.ninja, "-DREXSDK_DIR=" + self.sdk,
                   "-DREXGLUE_OUTPUT_ROOT=" + os.path.join(self.root, "out", "sdk"),
                      "-DREXGLUE_OUTPUT_ROOT=" + os.path.join(self.root, "out", "sdk"),
                      "-DBANJO_RENUT_EARLY_ALPHA=OFF", "-DMTG15_RENUT_PORT_SHADERS=OFF",
                      "-DPython3_EXECUTABLE=" + py, "-DPYTHON_EXECUTABLE=" + py])
            self.run([self.cmake, "--build", pc, "--target", "renut_xenos_recomp", "-j", str(self.args.jobs)])
            xenos = os.path.join(pc, "xenos_recomp", "build", "XenosRecomp", "XenosRecomp.exe")
        if self.args.deko_tools:
            if not self.dry:
                for folder, executable in (("spirv-cross-build", "spirv-cross.exe"), ("uam-build", "uam.exe")):
                    source = os.path.join(os.path.abspath(self.args.deko_tools), folder)
                    target = os.path.join(self.root, "out", "deko3d_tools", folder)
                    os.makedirs(target, exist_ok=True)
                    shutil.copy2(os.path.join(source, executable), os.path.join(target, executable))
                    for name in os.listdir(source):
                        if name.lower().endswith(".dll"): shutil.copy2(os.path.join(source, name), os.path.join(target, name))
        else:
            if not self.args.spirv_cross_source: raise ValueError("--spirv-cross-source or --deko-tools is required")
            self.run([self.bash, "tools/deko3d_build_tools.sh", os.path.abspath(self.args.spirv_cross_source)])
        spirv = os.path.join(self.path("shader_dir"), "spirv")
        cache_dir = os.path.join(pc, "renut_gpu")
        if not self.dry: os.makedirs(cache_dir, exist_ok=True)
        self.run([os.path.abspath(xenos), dump, os.path.join(cache_dir, "shader_cache.cpp"),
                  os.path.join(self.root, "app", "thirdparty", "reblue-XenosRecomp", "XenosRecomp", "shader_common.h")],
                 env={"BANJO_DEKO3D_SPIRV_DIR": spirv})
        self.run([py, os.path.join(self.root, "tools", "deko3d_shaders.py"), "--spirv", spirv,
                  "--out", self.path("shader_dir"), "--jobs", str(self.args.jobs)])
        glsl = os.path.join(self.path("shader_dir"), "glsl_opt")
        self.run([py, os.path.join(self.root, "tools", "deko3d_glsl_opt.py"),
                  "--in", os.path.join(self.path("shader_dir"), "glsl"), "--out", glsl, "--check"])
        self.run([py, os.path.join(self.root, "tools", "renut_switch_shader_cache.py"), "--pc", pc])
        self.run([py, os.path.join(self.root, "tools", "renut_release_shaders.py"), "--glsl", glsl])


    def selected_language(self, packaging=False):
        options_file = os.path.join(self.root, "out", "build_options.json")
        recorded = None
        if os.path.isfile(options_file):
            with open(options_file, encoding="utf-8") as stream:
                recorded = json.load(stream)["language"]
        requested = self.args.language
        if packaging and requested is not None and requested != (recorded or "system"):
            raise ValueError("Language differs from the built NRO; run the nro step with --language " + requested)
        return requested if requested is not None else (recorded or "system")

    def prepare_language(self):
        language = self.selected_language()
        value = "" if language == "system" else language
        self.say("   build language: " + language + "; controller glyphs: Nintendo Switch")
        if self.dry:
            return language
        for name in ("mtg15_switch_defaults.toml", "mtg15_switch.toml"):
            path = os.path.join(self.root, "app", name)
            with open(path, encoding="utf-8") as stream:
                text = stream.read()
            setting = 'mtg15_language = "' + value + '"'
            if re.search(r"(?m)^mtg15_language\s*=", text):
                text = re.sub(r"(?m)^mtg15_language\s*=.*$", setting, text)
            else:
                text += chr(10) + setting + chr(10)
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(text)
        return language

    def record_build_language(self, language):
        os.makedirs(os.path.join(self.root, "out"), exist_ok=True)
        with open(os.path.join(self.root, "out", "build_options.json"), "w", encoding="utf-8") as stream:
            json.dump({"language": language, "button_style": "switch"}, stream, indent=2)


    def do_nro(self):
        self.step("the NRO (devkitA64, Ninja)")
        language = self.prepare_language()
        build = self.path("build_dir")
        defines = ["-DMTG15_NATIVE_RENDERER=OFF", "-DMTG15_RENUT_RENDERER=ON", "-DMTG15_RENUT_PORT_SHADERS=OFF",
                   "-DMTG15_RENUT_RELEASE_SHADERS=ON", "-DMTG15_SWITCH_LTO=OFF", "-DMTG15_PGO=",
                   "-DREXSDK_DIR=" + self.sdk,
                   "-DREXGLUE_OUTPUT_ROOT=" + os.path.join(self.root, "out", "sdk"),
                   "-DREXGLUE_SWITCH_NVK_SDK=" + (self.nvk or "")]
        cmd = [self.cmake, "-S", os.path.join(self.root, "app"), "-B", build, "-G", "Ninja",
               "-DCMAKE_BUILD_TYPE=Release",
               "-DCMAKE_TOOLCHAIN_FILE=" + os.path.join(self.root, "tools", "switch", "cmake",
                                                         "switch-devkitA64.cmake"),
               "-DCMAKE_MAKE_PROGRAM=" + self.ninja,
               "-DPython3_EXECUTABLE=" + sys.executable, "-DPYTHON_EXECUTABLE=" + sys.executable] + defines
        self.run(cmd, what="configure for the console")
        self.run([self.cmake, "--build", build, "-j", str(self.args.jobs)], what="compile mtg15.nro")
        if not self.dry:
            self.record_build_language(language)

    # --- 9. assemble ---------------------------------------------------------------------------------------------
    def do_assemble(self):
        language = self.selected_language(packaging=True)
        self.step("the SD card folder: " + self.sd)
        nro = os.path.join(self.path("build_dir"), self.game["nro"])
        if not self.dry:
            os.makedirs(self.sd, exist_ok=True)
            shutil.copy2(nro, os.path.join(self.sd, self.game["nro"]))
            glsl = os.path.join(self.path("renut_release"), "sd", "deko3d_glsl.bin")
            if os.path.isfile(glsl):
                shutil.copy2(glsl, os.path.join(self.sd, "deko3d_glsl.bin"))
            else:
                sys.exit("Required shader package is missing: " + glsl)
            texture_file = os.path.join(self.root, "out", "mtg15_texturas.bin")
            if not os.path.isfile(texture_file): sys.exit("Switch button overrides are missing")
            shutil.copy2(texture_file, os.path.join(self.sd, "mtg15_texturas.bin"))
            cfg = self.game["switch_config"]
            lines = ["# " + self.game["title"] + " for the Nintendo Switch: your options.",
                     "# Written by the installer; the game also writes this file at its first start when it is missing.",
                     ""]
            keys = dict(cfg["keys"])
            keys["mtg15_language"] = "" if language == "system" else language
            for key, value in keys.items():
                if isinstance(value, bool):
                    lines.append("%s = %s" % (key, "true" if value else "false"))
                elif isinstance(value, str):
                    lines.append('%s = "%s"' % (key, value))
                else:
                    lines.append("%s = %s" % (key, value))
            with open(os.path.join(self.sd, cfg["toml"]), "w", encoding="utf-8") as fh:
                fh.write(chr(10).join(lines) + chr(10))
            if self.dlc:
                dlc_dir = os.path.join(self.sd, "dlc")
                os.makedirs(dlc_dir, exist_ok=True)
                for spec, path in self.dlc:
                    shutil.copy2(path, os.path.join(dlc_dir, spec["package"]))
        if not self.dry:
            manifest = os.path.join(self.out, "switch", "SHA256_mtg15-nx.txt")
            with open(manifest, "w", encoding="ascii") as stream:
                for base, dirs, files in os.walk(self.sd):
                    dirs.sort()
                    for name in sorted(files):
                        file_path = os.path.join(base, name)
                        rel = os.path.relpath(file_path, self.sd).replace(os.sep, "/")
                        stream.write(sha256(file_path) + " *./" + rel + chr(10))
        self.show_sd_folder()

    def show_sd_folder(self):
        self.say("")
        self.say("Copy this folder to the SD card:  sdmc:/switch/" + self.game["sdcard_folder"] + "/")
        self.say("")
        if os.path.isdir(self.sd):
            total = 0
            for base, dirs, files in os.walk(self.sd):
                rel = os.path.relpath(base, self.sd).replace(os.sep, "/")
                if rel == ".":
                    rel = ""
                for name in sorted(files):
                    p = os.path.join(base, name)
                    size = os.path.getsize(p)
                    total += size
                    self.say("   %-42s %10s" % ((rel + "/" if rel else "") + name, human(size)))
            self.say("")
            self.say("   %-42s %10s" % ("total", human(total)))
        self.say("")
        self.say("Launch it with a title takeover (hold R on a installed game and open the Homebrew Menu) or a")
        self.say("forwarder: from the Album applet it does not get enough memory. Copy the files over the ones on")
        self.say("the card, do not delete the folder: your settings and saved games live in it.")

    # --- toolchain -----------------------------------------------------------------------------------------------
    def find_toolchain(self):
        self.cmake = os.environ.get('CMAKE') or which('cmake')
        self.ninja = os.environ.get('NINJA') or which('ninja')
        self.clang = os.environ.get('MTG15_CLANG') or which('clang')
        self.clang_pp = os.environ.get('MTG15_CLANGXX') or which('clang++')
        self.bash = os.environ.get('MTG15_BASH') or which('bash')
        self.nvk = os.environ.get('MTG15_NVK_SDK') or ''
        vs = os.environ.get('MTG15_VSDIR') or 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools'
        cm = os.path.join(vs, 'Common7', 'IDE', 'CommonExtensions', 'Microsoft', 'CMake')
        if (not self.cmake or '/msys2/usr/bin/' in self.cmake.replace(chr(92), '/').lower()) and os.path.isfile(os.path.join(cm, 'CMake', 'bin', 'cmake.exe')):
            self.cmake = os.path.join(cm, 'CMake', 'bin', 'cmake.exe')
        if (not self.ninja or '/msys2/usr/bin/' in self.ninja.replace(chr(92), '/').lower()) and os.path.isfile(os.path.join(cm, 'Ninja', 'ninja.exe')):
            self.ninja = os.path.join(cm, 'Ninja', 'ninja.exe')
        devkit = os.environ.get('DEVKITPRO') or 'C:/devkitPro'
        if os.name == 'nt' and devkit.startswith('/opt/'):
            # devkitPro's installer sets the MSYS path; CMake on Windows cannot use it.
            devkit = 'C:/devkitPro'
        if not os.path.isdir(devkit) and os.path.isdir('/opt/devkitpro'):
            devkit = '/opt/devkitpro'
        self.devkitpro = devkit
        if os.path.isdir(devkit):
            os.environ['DEVKITPRO'] = devkit
        if sys.version_info < (3, 8):
            self.missing['python'] = 'Python 3.8 or newer (this is %d.%d)' % sys.version_info[:2]
        if not self.cmake:
            self.missing['cmake'] = ('CMake 3.25+ (https://cmake.org/download/, or the Visual Studio Build Tools)')
        if not self.ninja:
            self.missing['ninja'] = ('Ninja (with the Visual Studio Build Tools, or https://ninja-build.org/)')
        if not self.clang or not self.clang_pp:
            self.missing['clang'] = ('LLVM clang 20+ on the PATH (https://releases.llvm.org/) for the code generator and the PC build')
        if not self.bash:
            self.missing['bash'] = ('bash (Git for Windows, or the MSYS2 that comes with devkitPro) for tools/deko3d_build_tools.sh')
        if not os.path.isdir(devkit):
            self.missing['devkitpro'] = ('devkitPro with devkitA64 and libnx (https://devkitpro.org/wiki/Getting_Started); set DEVKITPRO if it is not in C:/devkitPro')
        try:
            import PIL  # noqa: F401
            import numpy  # noqa: F401
            import xxhash  # noqa: F401
            import zstandard  # noqa: F401
        except ImportError:
            self.missing['pillow'] = ('Pillow, numpy, xxhash and zstandard (py -m pip install Pillow numpy xxhash zstandard)')
        if not self.nvk or not os.path.isdir(self.nvk):
            print('   (no NVK SDK: fine, this port draws with deko3d and links no Vulkan driver)')


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="install.py", description="Build the Nintendo Switch folder of a Magic Duels port from your own game "
                                      "files. Nothing of the game is part of this repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python install/install.py --game mtg15 --xex default.xex --xexp default.xexp "
               "--data <game folder> --dlc <DLC folder> --out out")
    ap.add_argument("--game", default="mtg15", help="which game (install/games/<game>.json); mtg15")
    ap.add_argument("--xex", help="your default.xex")
    ap.add_argument("--xexp", help="the Title Update's default.xexp")
    ap.add_argument("--data", help="folder with the extracted base game and chosen TU ZED files")
    ap.add_argument("--tu", help="folder with the Title Update's UPDATE_DATA_001.ZED, if it is not with --data")
    ap.add_argument("--dlc", help="folder with the DLC packages (optional; searched recursively)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(REPO), "mtg15-output"), help="output folder outside the repository (default: ../mtg15-output)")
    ap.add_argument("--stage", help="staging folder for the game files (default: <out>/stage)")
    ap.add_argument("--sdk", help="SDK source tree (default: sdk/ in this repository)")
    ap.add_argument("--thirdparty", help="folder containing plume, uam, imgui and reblue-XenosRecomp")
    ap.add_argument("--icon", help="your NRO icon; converted to 256x256 JPEG locally")
    ap.add_argument("--spirv-cross-source", help="SPIRV-Cross sources for the host shader tools")
    ap.add_argument("--lua-dump", help="decrypted Lua dumps from your own PC run")
    ap.add_argument("--shader-dump", help="shader containers captured from your own PC run")
    ap.add_argument("--texture-dump", help="the two original converted texture captures")
    ap.add_argument("--rexglue", help="optional existing host code generator")
    ap.add_argument("--xenos-recomp", help="optional existing XenosRecomp.exe")
    ap.add_argument("--deko-tools", help="optional existing deko3d_tools directory")
    ap.add_argument("--language", choices=("system", "en", "es", "fr", "de", "it", "ja", "pt", "ko", "ru"),
                    default=None, help="language baked into the NRO: system (default), en, es, fr, de, it, ja, pt, ko, ru; reuses the staged choice for partial runs")
    ap.add_argument("--jobs", type=int, default=8, help="parallel compile jobs for the NRO (default: 8)")
    ap.add_argument("--dry-run", action="store_true", help="print the steps and their commands, run nothing")
    ap.add_argument("--only", help="run only these steps (comma separated)")
    ap.add_argument("--skip", help="run every step but these")
    ap.add_argument("--list-steps", action="store_true", help="print the steps and exit")
    args = ap.parse_args(argv)

    if args.list_steps:
        print("Steps of this installer:")
        for name, text in STEP_HELP:
            print("  %-10s %s" % (name, text))
        return 0
    if not os.path.isfile(os.path.join(GAMES, args.game + ".json")):
        ap.error("no install/games/%s.json (the games this installer knows)" % args.game)

    inst = Installer(args)
    inst.find_toolchain()
    print(inst.game['title'] + ' -> ' + inst.sd)
    if args.dry_run:
        print('(dry run: nothing is written)')

    steps = [name for name, _ in STEP_HELP]
    if args.only:
        wanted = [s.strip() for s in args.only.split(',') if s.strip()]
        steps = [s for s in steps if s in wanted]
    if args.skip:
        skip = [s.strip() for s in args.skip.split(',') if s.strip()]
        steps = [s for s in steps if s not in skip]
    needed = ['python'] + sorted(set(k for s in steps for k in STEP_TOOLS.get(s, ())))
    inst.ask_missing(needed)

    if any(name in steps for name in ("stage", "icons", "lua", "shaders", "assemble")) and "verify" not in steps:
        inst.do_verify()
    unknown = set((args.only or "").split(",")) - {""} - {name for name, _ in STEP_HELP}
    if unknown:
        ap.error("unknown steps: " + ", ".join(sorted(unknown)))
    handlers = {"verify": inst.do_verify, "stage": inst.do_stage, "icons": inst.do_icons,
                "lua": inst.do_lua, "pack": inst.do_pack, "codegen": inst.do_codegen,
                "shaders": inst.do_shaders, "nro": inst.do_nro, "assemble": inst.do_assemble}
    for name in steps:
        handlers[name]()
    print("")
    print("done" if not args.dry_run else "dry run finished: nothing was written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
