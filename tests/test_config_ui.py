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
    local cls = {_base = base}
    setmetatable(cls, {
        __index = base,
        __call = function(c, ...)
            local obj = setmetatable({}, {__index = c})
            if ctor then ctor(obj, ...) end
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
    function result.textbox:OnTextInput(...) return false, false end
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
    function result:RefreshView()
        for index, item in ipairs(data) do
            local row = self.rows[index]
            if row then self.update_fn(opts.scroll_context, row, item, index) end
        end
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
    {name="ai_1_api_key", label="AI 1 key", default="", saved="", options={{description="", data=""}}},
    {name="ai_2_api_key", label="AI 2 key", default="", saved="", options={{description="", data=""}}},
    {name="ai_3_api_key", label="AI 3 key", default="", saved="", options={{description="", data=""}}},
    {name="ai_4_api_key", label="AI 4 key", default="", saved="", options={{description="", data=""}}},
    {name="ai_5_api_key", label="AI 5 key", default="", saved="", options={{description="", data=""}}},
    {name="api_base_url", label="Base URL", default="https://api.openai.com/v1", saved="https://api.openai.com/v1", options={{description="OpenAI", data="https://api.openai.com/v1"}}},
    {name="model", label="Model", default="gpt-4o-mini", saved="gpt-4o-mini", options={{description="Model", data="gpt-4o-mini"}}},
    {name="request_interval", label="Interval", default=30, saved=30,
     options={{description="30", data=30}, {description="60", data=60}}},
}
SAVED = nil
SAVE_COUNT = 0
KnownModIndex = {
    LoadModConfigurationOptions = function(_, name, client) return CONFIG end,
    GetModInfo = function(_, name) return {client_only_mod=false} end,
    GetModFancyName = function(_, name) return "AI Players" end,
    SaveConfigurationOptions = function(_, callback, name, settings, client)
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
        elif NATIVE_SCREEN.is_file():
            native_source = NATIVE_SCREEN.read_text(encoding="utf-8")
        else:
            self.skipTest("set DST_SCRIPTS_ZIP to the game's data/databundles/scripts.zip")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.modules = {}
        self.lua.execute(MOCK_ENGINE)

        def require(name):
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

        # All five keys, including duplicate values and clearing an empty key, commit
        # through the text-entry callback and mark the native screen dirty.
        values = {
            "ai_1_api_key": "shared-secret",
            "ai_2_api_key": "shared-secret",
            "ai_3_api_key": "",
            "ai_4_api_key": "fourth-secret",
            "ai_5_api_key": "fifth-secret",
            "api_base_url": "https://gateway.example/v1",
            "model": "custom-model",
        }
        for name, value in values.items():
            entry = row(name).ai_text_entry.textbox
            entry.SetString(entry, value)
            entry.OnTextInputted(entry)
            self.assertEqual(entry.GetString(entry), value)
            self.assertTrue(row(name).ai_option_data.selected_value == value)
        self.assertTrue(screen.IsDirty(screen))
        self.assertTrue(row("ai_1_api_key").ai_text_entry.textbox.password)
        self.assertFalse(row("model").ai_text_entry.textbox.password)

        # RefreshView recycles the native rows but must retain every edited value.
        screen.options_scroll_list.RefreshView(screen.options_scroll_list)
        for name, value in values.items():
            self.assertEqual(row(name).ai_text_entry.textbox.GetString(row(name).ai_text_entry.textbox), value)
            self.assertEqual(row(name).ai_option_data.option.value, value)

        # A recycled row switches back to its spinner, then binds a text option again.
        recycled = row("ai_1_api_key")
        grid = screen.options_scroll_list
        grid.update_fn(None, recycled, screen.optionwidgets[1], 1)
        self.assertFalse(recycled.ai_text_entry.shown)
        self.assertTrue(recycled.opt.spinner.shown)
        grid.update_fn(None, recycled, screen.optionwidgets[2], 2)
        self.assertTrue(recycled.ai_text_entry.shown)
        self.assertEqual(recycled.ai_text_entry.textbox.GetString(recycled.ai_text_entry.textbox), values["ai_1_api_key"])

        # Apply and reopen with persisted arbitrary strings, including duplicate keys.
        screen.Apply(screen)
        self.assertEqual(self.lua.globals().SAVE_COUNT, 1)
        saved = {item.name: item.saved for _, item in self.lua.globals().SAVED.items()}
        for name, value in values.items():
            self.assertEqual(saved[name], value)
        screen = self.require("screens/redux/modconfigurationscreen")("ai_players", False)
        hooks[0][1](screen, "ai_players")
        for name, value in values.items():
            self.assertEqual(row(name).ai_text_entry.textbox.GetString(row(name).ai_text_entry.textbox), value)

        # Native Reset uses its confirmation callback and RefreshView; it restores
        # defaults in both the data model and the visible entries.
        screen.ResetToDefaultValues(screen)
        popup = self.lua.globals().TheFrontEnd.pushed
        self.assertIsNotNone(popup)
        popup.buttons[1].cb()
        self.assertEqual(row("ai_1_api_key").ai_text_entry.textbox.GetString(row("ai_1_api_key").ai_text_entry.textbox), "")
        self.assertEqual(row("api_base_url").ai_text_entry.textbox.GetString(row("api_base_url").ai_text_entry.textbox), "https://api.openai.com/v1")
        self.assertEqual(row("model").ai_text_entry.textbox.GetString(row("model").ai_text_entry.textbox), "gpt-4o-mini")

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
        second_row = next(r for _, r in second.options_scroll_list.rows.items()
                          if r.ai_option_data and r.ai_option_data.option.name == "model")
        second_row.ai_text_entry.textbox.SetString(second_row.ai_text_entry.textbox, "discard-me")
        second_row.ai_text_entry.textbox.OnTextInputted(second_row.ai_text_entry.textbox)
        second.Cancel(second)
        cancel_popup = self.lua.globals().TheFrontEnd.pushed
        cancel_popup.buttons[1].cb()
        self.assertEqual(self.lua.globals().SAVE_COUNT, 2)


if __name__ == "__main__":
    unittest.main()
