"""Native DST ModConfigurationScreen regression coverage via lupa.lua51.

The native screen comes from local_reference or DST_SCRIPTS_ZIP (the game's
scripts.zip). Only the engine/widget shell is mocked; no game source is bundled.
Requires: python -m pip install lupa
"""
from __future__ import annotations

import os
import pathlib
import unittest
import zipfile

try:
    from lupa.lua51 import LuaRuntime
except ImportError:  # pragma: no cover - makes the dependency failure explicit
    LuaRuntime = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE_SCREEN = ROOT / "local_reference" / "modconfigurationscreen.lua"
CONFIG_UI = ROOT / "scripts" / "ai_players_config_ui.lua"
SERVER_ENTRY = ROOT / "modservercreationmain.lua"


MOCK_ENGINE = r'''
local function widget(name)
    local self = {name = name, children = {}, shown = true}
    function self:AddChild(child) table.insert(self.children, child); return child end
    function self:InsertWidget(child) table.insert(self.children, child); return child end
    function self:SetPosition(...) end
    function self:SetSize(...) end
    function self:SetRegionSize(...) end
    function self:SetVAnchor(...) end
    function self:SetHAnchor(...) end
    function self:SetScaleMode(...) end
    function self:SetColour(...) end
    function self:SetVAlign(...) end
    function self:SetHAlign(...) end
    function self:EnableWordWrap(...) end
    function self:SetString(value) self.string = value end
    function self:GetString() return self.string or "" end
    function self:GetRegionSize() return 100 end
    function self:SetTruncatedString(value) self.string = value end
    function self:Show() self.shown = true end
    function self:Hide() self.shown = false end
    function self:SetCanFadeAlpha(...) end
    function self:SetHasModification(value) self.modified = value end
    function self:EnablePendingModificationBackground() end
    function self:SetSelected(value) self.selected = value end
    function self:SetOptions(value) self.options = value end
    function self:SetSize(...) end
    function self:EnableRegionSizeLimit(...) end
    function self:EnableScrollEditWindow(...) end
    function self:SetTextLengthLimit(...) end
    function self:SetAllowNewline(...) end
    function self:SetEditing(value) self.editing = value end
    function self:SetPassword(value) self.password = value end
    function self:GetString() return self.string or "" end
    function self:SetOnGainFocus(callback) self.on_gain_focus = callback end
    return self
end

Widget = setmetatable(widget("Widget"), {__call = function(_, name) return widget(name) end})

local function class(base, ctor)
    local cls = {_base = base, _ctor = ctor}
    setmetatable(cls, {
        __index = base,
        __call = function(c, ...)
            local obj = setmetatable({}, {__index = c})
            if c._ctor then c._ctor(obj, ...) end
            return obj
        end,
    })
    return cls
end
Class = class
Screen = class(Widget, function(self, name)
    self.name = name
    self.children = {}
end)
function Screen._ctor(self, name) self.name = name; self.children = {} end
function Screen:OnControl(...) return false end
function Screen:HookupFocusMoves() end

local function label_spinner()
    local result = widget("labelspinner")
    result.label = widget("label")
    result.spinner = widget("spinner")
    result:AddChild(result.label)
    result:AddChild(result.spinner)
    return result
end

local function text_entry()
    local result = widget("textentry")
    result.textbox = widget("textbox")
    result.textbox.string = ""
    result.textbox.conversions = {}
    result.textbox.inst = {TextEditWidget = {
        OnTextInput = function(_, text) result.textbox.string = result.textbox.string .. text end,
    }}
    function result.textbox:ValidateChar(text) return true end
    function result.textbox:OnTextInput(text) return native_text_input(self, text) end
    function result.textbox:OnTextInputted(...) end
    function result.textbox:OnTextEntered(...) end
    result:AddChild(result.textbox)
    return result
end

local function scrolling_grid(data, opts)
    local result = widget("scrollinggrid")
    result.visible_rows = opts.num_visible_rows
    result.update_fn = opts.apply_fn
    result.rows = {}
    for index, item in ipairs(data) do
        local row = opts.item_ctor_fn(opts.scroll_context, index)
        result.rows[index] = row
        result.update_fn(opts.scroll_context, row, item, index)
    end
    result.items = data
    function result:RefreshView()
        for index, row in ipairs(self.rows) do
            self.update_fn(opts.scroll_context, row, self.items[index], index)
        end
    end
    function result:SetItemsData(items)
        self.items = items
        self:RefreshView()
    end
    function result:OnWidgetFocus(...) end
    return result
end

__mock_modules = {}
__mock_modules["util"] = {}
__mock_modules["strings"] = {}
__mock_modules["constants"] = {}
__mock_modules["stringutil"] = {}
__mock_modules["widgets/widget"] = Widget
__mock_modules["widgets/screen"] = Screen
__mock_modules["widgets/image"] = function(...) return widget("image") end
__mock_modules["widgets/text"] = function(...) return widget("text") end
__mock_modules["screens/redux/popupdialog"] = function(title, body, buttons)
    return {title = title, body = body, buttons = buttons}
end
__mock_modules["widgets/redux/templates"] = {
    BackgroundTint = function() return widget("background") end,
    ScreenRoot = function() return widget("root") end,
    RectangleWindow = function(...) local w = widget("window"); w.actions = widget("actions"); return w end,
    ListItemBackground = function(...) return widget("background") end,
    LabelSpinner = label_spinner,
    StandardSingleLineTextEntry = text_entry,
    ScrollingGrid = scrolling_grid,
}

STRINGS = {UI = {MODSSCREEN = {
    APPLY = "Apply", RESETDEFAULT = "Reset", BACK = "Back",
    CONFIGSCREENTITLESUFFIX = " Configuration", UNKNOWN_MOD_CONFIG_SETTING = "Unknown",
    BACKTITLE = "Back", BACKBODY = "Discard?", YES = "Yes", NO = "No",
}}}
HEADERFONT = "header"; CHATFONT = "chat"
UICOLOURS = {GOLD_SELECTED = {}, GOLD_UNIMPORTANT = {}, GOLD = {}}
ANCHOR_MIDDLE = 0; ANCHOR_TOP = 0; SCALEMODE_PROPORTIONAL = 0
TheInput = {ControllerAttached = function() return false end}
TheFrontEnd = {
    popped = 0,
    pushed = nil,
    PopScreen = function(self) self.popped = self.popped + 1 end,
    PushScreen = function(self, screen) self.pushed = screen end,
}

MOD_NAME = "ai_players"
CONFIG = {
    {name="ai_count", label="AI count", default=0, saved=0,
     options={{description="0", data=0}, {description="1", data=1}}},
}
for index = 1, 5 do
    for _, field in ipairs({"api_base_url", "api_key", "model"}) do
        table.insert(CONFIG, {
            name="ai_" .. index .. "_" .. field,
            label="AI " .. index .. " " .. field,
            default="", saved="", options={{description="", data=""}},
        })
    end
end
table.insert(CONFIG, {
    name="request_interval", label="Interval", default=30, saved=30,
    options={{description="30", data=30}, {description="60", data=60}},
})
table.insert(CONFIG, {
    name="api_base_url", label="Legacy URL", default="https://api.openai.com/v1",
    saved="https://legacy.example/v1", options={{description="OpenAI", data="https://api.openai.com/v1"}},
})
table.insert(CONFIG, {
    name="model", label="Legacy model", default="gpt-4o-mini", saved="legacy-model",
    options={{description="Model", data="gpt-4o-mini"}},
})
SAVED = nil
SAVE_COUNT = 0
KnownModIndex = {
    LoadModConfigurationOptions = function(_, name, client) return CONFIG end,
    GetModInfo = function(_, name) return {client_only_mod=false} end,
    GetModFancyName = function(_, name) return "AI Players" end,
    SaveConfigurationOptions = function(_, callback, name, settings, client)
        SAVED_CLIENT_CONFIG = client
        SAVE_COUNT = SAVE_COUNT + 1
        CONFIG = settings
        SAVED = settings
        callback()
    end,
}
'''


class ConfigUIScreenTest(unittest.TestCase):
    def setUp(self) -> None:
        if LuaRuntime is None:
            self.skipTest("lupa.lua51 is required: pip install lupa")
        if os.environ.get("DST_SCRIPTS_ZIP"):
            with zipfile.ZipFile(os.environ["DST_SCRIPTS_ZIP"]) as archive:
                member = next(name for name in archive.namelist()
                              if name.endswith("screens/redux/modconfigurationscreen.lua"))
                native_source = archive.read(member).decode("utf-8")
                textedit_source = archive.read("scripts/widgets/textedit.lua").decode("utf-8")
        elif NATIVE_SCREEN.is_file():
            native_source = NATIVE_SCREEN.read_text(encoding="utf-8")
            textedit_source = (NATIVE_SCREEN.parent / "textedit.lua").read_text(encoding="utf-8")
        else:
            self.skipTest("set DST_SCRIPTS_ZIP to the game's data/databundles/scripts.zip")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.modules = {}
        self.lua.execute(MOCK_ENGINE)
        text_input = textedit_source.split("function TextEdit:OnTextInput(text)", 1)[1]
        text_input = text_input.split("function TextEdit:OnProcess()", 1)[0]
        self.lua.execute("TextEdit = {}; function TextEdit:OnTextInput(text)" + text_input)
        self.lua.globals().native_text_input = self.lua.globals().TextEdit.OnTextInput

        def require(name):
            loaded = self.lua.globals().package.loaded[name]
            if loaded is not None:
                return loaded
            if name in self.modules:
                return self.modules[name]
            mocks = self.lua.eval("__mock_modules")
            mock = mocks[name]
            if mock is not None:
                self.modules[name] = mock
                return mock
            path = {
                "screens/redux/modconfigurationscreen": NATIVE_SCREEN,
                "ai_players_config_ui": CONFIG_UI,
                "modservercreationmain": SERVER_ENTRY,
            }.get(name)
            if path is None:
                raise AssertionError(f"unexpected Lua require: {name}")
            source = native_source if path == NATIVE_SCREEN else path.read_text(encoding="utf-8")
            module = self.lua.execute(source)
            self.modules[name] = module if module is not None else True
            return self.modules[name]

        self.lua.globals().require = require
        self.require = require

    def test_configuration_open_before_server_enable(self) -> None:
        # Metadata is evaluated in the game's restricted environment, with no
        # require/GLOBAL fallback. The enabled CLIENT helper boots separately.
        metadata = self.lua.eval('''function(code)
            local env = {folder_name="ai_players"}
            setfenv(assert(loadstring(code)), env)()
            return env
        end''')((ROOT / "modinfo.lua").read_text(encoding="utf-8"))
        self.lua.globals().MOD_METADATA = metadata
        self.lua.execute('''
            GLOBAL = _G
            MODS_ROOT = "mods/"
            CONFIG = MOD_METADATA.configuration_options
            function KnownModIndex:GetModNames() return {"ai_players", "other_mod"} end
            function KnownModIndex:GetModInfo(name)
                return name == "ai_players" and MOD_METADATA or {client_only_mod=true}
            end
            function AddClassPostConstruct(path, callback)
                local cls = require(path)
                local ctor = cls._ctor
                cls._ctor = function(self, ...) ctor(self, ...); callback(self, ...) end
            end
        ''')
        def load_script(path):
            self.assertEqual(path, "mods/ai_players/scripts/ai_players_config_ui.lua")
            return self.lua.eval("loadstring")(CONFIG_UI.read_text(encoding="utf-8"))
        self.lua.globals().kleiloadlua = load_script
        def modimport(name):
            self.lua.execute((ROOT / "client_config_helper" / name).read_text(encoding="utf-8"))
        self.lua.globals().modimport = modimport
        self.lua.execute((ROOT / "client_config_helper/modmain.lua").read_text(encoding="utf-8"))
        # Repeated helper activation and the standard server entry stay idempotent.
        self.lua.execute((ROOT / "client_config_helper/modservercreationmain.lua").read_text(encoding="utf-8"))
        self.lua.globals().modname = "ai_players"
        self.require("modservercreationmain")
        screen = self.require("screens/redux/modconfigurationscreen")("ai_players", True)
        self.assertFalse(screen.client_config, "settings must reach the server, not the CLIENT file")
        rows = list(screen.options_scroll_list.rows.values())
        self.assertEqual(len([row for row in rows if row.ai_option_data is not None]), 0)
        count_row = next(row for row in rows if row.opt.data is not None
                         and row.opt.data.option.name == "ai_count")
        count_row.opt.spinner.OnChanged(count_row.opt.spinner, 3)
        displayed = screen.options_scroll_list["items"]
        expected = [f"ai_{i}_{field}" for i in range(1, 4)
                    for field in ("api_base_url", "api_key", "model")]
        self.assertEqual([displayed[i].option.name for i in range(1, len(displayed) + 1)],
                         ["ai_count", *expected, "request_interval"])
        self.assertEqual(len([row for row in rows if row.ai_option_data is not None]), 9)
        keys = [row for row in rows if row.ai_option_data is not None
                and row.ai_option_data.option.name.endswith("_api_key")]
        self.assertEqual(len(keys), 3)
        for row in keys:
            entry = row.ai_text_entry.textbox
            entry.SetEditing(entry, True)
            for char in "fixture-key":
                result = entry.OnTextInput(entry, char)
                self.assertTrue(result[0])
            self.assertEqual(entry.GetString(entry), "fixture-key")
            self.assertEqual(row.ai_option_data.option.value, "fixture-key")
        screen.Apply(screen)
        self.assertFalse(self.lua.globals().SAVED_CLIENT_CONFIG)
        # A different client mod retains the native client-settings destination.
        other = self.require("screens/redux/modconfigurationscreen")("other_mod", True)
        self.assertTrue(other.client_config)
        self.assertFalse(other.ai_players_configured or False)

    def test_fields_follow_ai_count_without_losing_values(self) -> None:
        self.lua.execute('''
            function AddClassPostConstruct(path, callback)
                local cls = require(path)
                local ctor = cls._ctor
                cls._ctor = function(self, ...)
                    ctor(self, ...)
                    callback(self, ...)
                end
            end
            modname = "ai_players"
        ''')
        self.require("modservercreationmain")
        screen = self.require("screens/redux/modconfigurationscreen")("ai_players", False)

        def visible(name=None):
            return [row for _, row in screen.options_scroll_list.rows.items()
                    if row.ai_option_data is not None
                    and (name is None or row.ai_option_data.option.name == name)]

        for count in (0, 1, 3, 5, 2, 0, 5):
            count_row = next(row for _, row in screen.options_scroll_list.rows.items()
                             if row.opt.data is not None and row.opt.data.option.name == "ai_count")
            count_row.opt.spinner.OnChanged(count_row.opt.spinner, count)
            expected_names = [f"ai_{i}_{field}" for i in range(1, count + 1)
                              for field in ("api_base_url", "api_key", "model")]
            self.assertEqual(len(visible()), count * 3)
            displayed = screen.options_scroll_list["items"]
            self.assertEqual([displayed[i].option.name for i in range(1, len(displayed) + 1)],
                             ["ai_count", *expected_names, "request_interval"])
            self.assertEqual({row.ai_option_data.option.name for row in visible()},
                             set(expected_names))
            for row in visible():
                name = row.ai_option_data.option.name
                entry = row.ai_text_entry.textbox
                self.assertEqual(entry.password, name.endswith("_api_key"))
                value = "fixture-" + name
                if entry.GetString(entry):
                    self.assertEqual(entry.GetString(entry), value)
                entry.SetString(entry, value)
                entry.OnTextInputted(entry)
            interval = next(row for _, row in screen.options_scroll_list.rows.items()
                            if row.opt.data is not None and row.opt.data.option.name == "request_interval")
            interval.opt.spinner.OnChanged(interval.opt.spinner, 60)
            settings = {item.name: item.saved for _, item in screen.CollectSettings(screen).items()}
            self.assertEqual(settings["request_interval"], 60)
            self.assertEqual(settings["ai_count"], count)
        screen.ResetToDefaultValues(screen)
        self.lua.globals().TheFrontEnd.pushed.buttons[1].cb()
        self.assertEqual(len([r for r in visible() if r.ai_option_data.option.name.endswith("_api_key")]), 0)

    def test_native_screen_text_configuration_lifecycle(self) -> None:
        # RED baseline: native DST rows are spinner-only before the mod postconstruct.
        screen = self.require("screens/redux/modconfigurationscreen")("ai_players", False)
        self.assertFalse(any(row["ai_text_entry"] is not None for _, row in screen.options_scroll_list.rows.items()))

        hooks = []

        def add_postconstruct(path, callback):
            hooks.append((path, callback))

        self.lua.globals().AddClassPostConstruct = add_postconstruct
        self.lua.globals().modname = "ai_players"
        self.require("modservercreationmain")
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0][0], "screens/redux/modconfigurationscreen")

        # Re-registration is idempotent.
        config_ui = self.require("ai_players_config_ui")
        config_ui.Register("ai_players", add_postconstruct)
        self.assertEqual(len(hooks), 1)

        hooks[0][1](screen, "unrelated_mod")
        self.assertFalse(any(row["ai_text_entry"] is not None for _, row in screen.options_scroll_list.rows.items()))
        hooks[0][1](screen, "ai_players")

        def row(name):
            for _, candidate in screen.options_scroll_list.rows.items():
                if candidate.ai_option_data and candidate.ai_option_data.option.name == name:
                    return candidate
            raise AssertionError(name)

        # All five keys are visible only after selecting five companions.
        count_row = next(r for _, r in screen.options_scroll_list.rows.items()
                         if r.opt.data is not None and r.opt.data.option.name == "ai_count")
        count_row.opt.spinner.OnChanged(count_row.opt.spinner, 5)

        # Each bot has its own URL/model; keys may duplicate or remain empty.
        values = {
            f"ai_{index}_{field}": value
            for index in range(1, 6)
            for field, value in (
                ("api_base_url", f"https://gateway-{index}.example/v1"),
                ("api_key", "shared-secret" if index < 3 else
                 "" if index == 3 else f"secret-{index}"),
                ("model", f"custom-model-{index}"),
            )
        }
        for name, value in values.items():
            entry = row(name).ai_text_entry.textbox
            entry.SetString(entry, value)
            entry.OnTextInputted(entry)
            self.assertEqual(entry.GetString(entry), value)
            self.assertTrue(row(name).ai_option_data.selected_value == value)
        self.assertTrue(screen.IsDirty(screen))
        self.assertTrue(row("ai_1_api_key").ai_text_entry.textbox.password)
        self.assertFalse(row("ai_1_api_base_url").ai_text_entry.textbox.password)
        self.assertFalse(row("ai_1_model").ai_text_entry.textbox.password)

        # RefreshView recycles the native rows but must retain every edited value.
        screen.options_scroll_list.RefreshView(screen.options_scroll_list)
        for name, value in values.items():
            self.assertEqual(row(name).ai_text_entry.textbox.GetString(row(name).ai_text_entry.textbox), value)
            self.assertEqual(row(name).ai_option_data.option.value, value)

        # Recycle a password row into plain URL/model fields and a spinner.
        recycled = row("ai_1_api_key")
        grid = screen.options_scroll_list
        self.assertTrue(recycled.ai_text_entry.textbox.password)
        grid.update_fn(None, recycled, screen.optionwidgets[2], 2)
        self.assertTrue(recycled.ai_text_entry.shown)
        self.assertFalse(recycled.ai_text_entry.textbox.password)
        self.assertEqual(recycled.ai_text_entry.textbox.GetString(recycled.ai_text_entry.textbox),
                         values["ai_1_api_base_url"])
        grid.update_fn(None, recycled, screen.optionwidgets[4], 4)
        self.assertFalse(recycled.ai_text_entry.textbox.password)
        self.assertEqual(recycled.ai_text_entry.textbox.GetString(recycled.ai_text_entry.textbox),
                         values["ai_1_model"])
        grid.update_fn(None, recycled, screen.optionwidgets[1], 1)
        self.assertFalse(recycled.ai_text_entry.shown)
        self.assertTrue(recycled.opt.spinner.shown)
        grid.update_fn(None, recycled, screen.optionwidgets[3], 3)
        self.assertTrue(recycled.ai_text_entry.shown)
        self.assertTrue(recycled.ai_text_entry.textbox.password)
        self.assertEqual(recycled.ai_text_entry.textbox.GetString(recycled.ai_text_entry.textbox), values["ai_1_api_key"])

        # Apply with bots 3-5 hidden, then reopen and reveal their retained values.
        count_row.opt.spinner.OnChanged(count_row.opt.spinner, 2)
        screen.Apply(screen)
        self.assertEqual(self.lua.globals().SAVE_COUNT, 1)
        saved = {item.name: item.saved for _, item in self.lua.globals().SAVED.items()}
        self.assertEqual(saved["api_base_url"], "https://legacy.example/v1")
        self.assertEqual(saved["model"], "legacy-model")
        for name, value in values.items():
            self.assertEqual(saved[name], value)
        screen = self.require("screens/redux/modconfigurationscreen")("ai_players", False)
        hooks[0][1](screen, "ai_players")
        count_row = next(r for _, r in screen.options_scroll_list.rows.items()
                         if r.opt.data is not None and r.opt.data.option.name == "ai_count")
        count_row.opt.spinner.OnChanged(count_row.opt.spinner, 5)
        for name, value in values.items():
            self.assertEqual(row(name).ai_text_entry.textbox.GetString(row(name).ai_text_entry.textbox), value)

        # Native Reset uses its confirmation callback and RefreshView; it restores
        # defaults in both the data model and the visible entries.
        screen.ResetToDefaultValues(screen)
        popup = self.lua.globals().TheFrontEnd.pushed
        self.assertIsNotNone(popup)
        popup.buttons[1].cb()
        self.assertFalse(any(r.ai_option_data is not None
                             for _, r in screen.options_scroll_list.rows.items()))
        reset_values = {item.name: item.saved for _, item in screen.CollectSettings(screen).items()}
        for name in values:
            self.assertEqual(reset_values[name], "")

        # Apply persists native CollectSettings output, including empty and duplicate keys.
        screen.Apply(screen)
        self.assertEqual(self.lua.globals().SAVE_COUNT, 2)
        saved = self.lua.globals().SAVED
        saved_by_name = {item.name: item.saved for _, item in saved.items()}
        self.assertEqual(saved_by_name["ai_1_api_key"], "")
        self.assertEqual(saved_by_name["ai_2_api_key"], "")
        self.assertEqual(saved_by_name["model"], "gpt-4o-mini")

        # A fresh screen proves Cancel does not invoke persistence after an edit.
        second = self.require("screens/redux/modconfigurationscreen")("ai_players", False)
        hooks[0][1](second, "ai_players")
        second_count = next(r for _, r in second.options_scroll_list.rows.items()
                            if r.opt.data is not None and r.opt.data.option.name == "ai_count")
        second_count.opt.spinner.OnChanged(second_count.opt.spinner, 1)
        second_row = next(r for _, r in second.options_scroll_list.rows.items()
                          if r.ai_option_data and r.ai_option_data.option.name == "ai_1_model")
        second_row.ai_text_entry.textbox.SetString(second_row.ai_text_entry.textbox, "discard-me")
        second_row.ai_text_entry.textbox.OnTextInputted(second_row.ai_text_entry.textbox)
        second.Cancel(second)
        cancel_popup = self.lua.globals().TheFrontEnd.pushed
        cancel_popup.buttons[1].cb()
        self.assertEqual(self.lua.globals().SAVE_COUNT, 2)


if __name__ == "__main__":
    unittest.main()
