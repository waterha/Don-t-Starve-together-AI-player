@echo off
setlocal
set "DEST=E:\WeGameApps\rail_apps\饥荒：联机版(2000004)\mods"
set "SRC=%~dp0"
echo This installer updates AI Players and its separate configuration helper.
echo It does not change world saves, modoverrides.lua, or API key settings.
echo.
echo Copying main mod...
xcopy "%SRC%ai_players\*" "%DEST%\ai_players\" /E /I /Y
echo.
echo Copying configuration helper...
xcopy "%SRC%ai_players_config\*" "%DEST%\ai_players_config\" /E /I /Y
echo.
echo Update complete. Restart the game before editing settings.
echo Re-enter the AI API key in the updated settings screen, then Apply and restart the world.
pause
