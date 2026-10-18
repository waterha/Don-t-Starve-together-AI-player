local TEMPLATES = require("widgets/redux/templates")

local ConfigUI = {}
local registered_mods = {}
local hook_installed = false

local function ai_option_index(name)
    local index, field = name:match("^ai_([1-5])_(.+)$")
    if field == "api_base_url" or field == "api_key" or field == "model" then
        return tonumber(index)
    end
end

local function is_text_option(name)
    return ai_option_index(name) ~= nil
end

local function configure_screen(screen)
    if screen.ai_players_configured then
        return
    end
    screen.ai_players_configured = true
    local list = screen.options_scroll_list
    local apply_data = list.update_fn
    local refresh_view = list.RefreshView
    local displayed_count

    -- Keep the complete option list for Apply/Reset. Filter only the displayed
    -- rows so hidden per-AI values and legacy fallback settings are preserved.
    list.RefreshView = function(self, ...)
        local count = 0
        for _, data in ipairs(screen.optionwidgets) do
            if data.option.name == "ai_count" then
                count = math.max(0, math.min(5, tonumber(data.selected_value) or 0))
                break
            end
        end
        if displayed_count ~= count then
            displayed_count = count
            local visible = {}
            for _, data in ipairs(screen.optionwidgets) do
                local name = data.option.name
                local index = ai_option_index(name)
                if name ~= "api_base_url" and name ~= "model"
                    and (index == nil or index <= count) then
                    table.insert(visible, data)
                end
            end
            -- Native SetItemsData calls RefreshView again; the count is already
            -- recorded, so that call renders without recursing into filtering.
            self:SetItemsData(visible)
            return
        end
        return refresh_view(self, ...)
    end

    list.update_fn = function(context, widget, data, index)
        if widget.ai_text_entry and widget.ai_option_data ~= data then
            widget.ai_text_entry.textbox:SetEditing(false)
        end
        apply_data(context, widget, data, index)
        widget.ai_option_data = nil

        -- Native callbacks address options by row index. Filtering changes that
        -- index, so use the bound option instead (also for the interval spinner).
        widget.opt.spinner.OnChanged = function(spinner, value)
            local bound = widget.opt.data
            if not bound then
                return
            end
            bound.option.value = value
            bound.selected_value = value
            spinner:SetHasModification(value ~= bound.initial_value)
            widget:ApplyDescription()
            screen:MakeDirty()
            if bound.option.name == "ai_count" then
                list:RefreshView()
            end
        end

        if not data or not is_text_option(data.option.name) then
            if widget.ai_text_entry then
                widget.ai_text_entry:Hide()
            end
            widget.opt.focus_forward = widget.opt.spinner
            return
        end

        if not widget.ai_text_entry then
            local entry = widget.opt:AddChild(TEMPLATES.StandardSingleLineTextEntry("", 225, 36))
            entry:SetPosition(150, 0)
            entry.textbox:SetAllowNewline(false)
            entry.textbox:SetTextLengthLimit(4096)
            entry.textbox:EnableRegionSizeLimit(false)
            entry.textbox:EnableScrollEditWindow(true)
            entry.focus_forward = entry.textbox
            widget.ai_text_entry = entry

            local function commit()
                local bound = widget.ai_option_data
                if not bound then
                    return
                end
                local value = entry.textbox:GetString()
                if value ~= bound.selected_value then
                    bound.selected_value = value
                    bound.option.value = value
                    screen:MakeDirty()
                end
            end

            local on_text_input = entry.textbox.OnTextInput
            entry.textbox.OnTextInput = function(textbox, ...)
                local handled, overflow = on_text_input(textbox, ...)
                commit()
                return handled, overflow
            end
            entry.textbox.OnTextInputted = commit
            entry.textbox.OnTextEntered = commit
            local on_lose_focus = entry.textbox.OnLoseFocus
            entry.textbox.OnLoseFocus = function(textbox, ...)
                commit()
                return on_lose_focus(textbox, ...)
            end
        end

        widget.ai_option_data = data
        widget.opt.spinner:Hide()
        local entry = widget.ai_text_entry
        entry:Show()
        entry.textbox:SetPassword(data.option.name:match("^ai_[1-5]_api_key$") ~= nil)
        local value = data.selected_value or ""
        if entry.textbox:GetString() ~= value then
            entry.textbox:SetString(value)
        end
        widget.opt.focus_forward = entry
    end

    list:RefreshView()
end

function ConfigUI.Register(mod_name, add_class_post_construct)
    registered_mods[mod_name] = true
    if hook_installed then
        return
    end
    hook_installed = true
    add_class_post_construct("screens/redux/modconfigurationscreen", function(screen, configured_mod)
        if registered_mods[configured_mod] then
            configure_screen(screen)
        end
    end)
end

return ConfigUI
