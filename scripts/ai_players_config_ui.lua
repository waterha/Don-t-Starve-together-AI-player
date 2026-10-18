local TEMPLATES = require("widgets/redux/templates")

local ConfigUI = {}
local registered_mods = {}
local hook_installed = false

local function is_key(name)
    return name:match("^ai_[1-5]_api_key$") ~= nil
end

local function is_text_option(name)
    return is_key(name) or name == "api_base_url" or name == "model"
end

local function configure_screen(screen)
    local list = screen.options_scroll_list
    local apply_data = list.update_fn

    list.update_fn = function(context, widget, data, index)
        -- Rows are recycled by TrueScrollList. Stop editing before rebinding.
        if widget.ai_text_entry and widget.ai_option_data ~= data then
            widget.ai_text_entry.textbox:SetEditing(false)
        end
        apply_data(context, widget, data, index)
        widget.ai_option_data = nil

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

            -- OnTextInput covers typing/paste; OnTextInputted covers deletion.
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
        entry.textbox:SetPassword(is_key(data.option.name))
        -- Avoid resetting the cursor when the scroller refreshes the same row.
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
