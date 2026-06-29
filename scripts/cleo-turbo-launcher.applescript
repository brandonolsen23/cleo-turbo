-- Cleo Turbo launcher
-- Opens Terminal with two tabs: backend (uvicorn :8099) and frontend (vite :5174)

set projectDir to "/Users/brandonolsen23/cleo-turbo"
set backendCmd to "cd " & quoted form of projectDir & " && printf '\\033]0;Cleo Backend\\007' && echo '\\033[1;32m▶ Cleo Backend — http://localhost:8099\\033[0m' && uvicorn cleo.web.app:app --reload --port 8099"
set frontendCmd to "cd " & quoted form of (projectDir & "/frontend") & " && printf '\\033]0;Cleo Frontend\\007' && echo '\\033[1;32m▶ Cleo Frontend — http://localhost:5174\\033[0m' && npm run dev"

tell application "Terminal"
	activate
	-- First tab: backend (opens new window)
	set backendTab to do script backendCmd
	set backendWindow to front window
	delay 0.3

	-- Second tab: frontend (new tab in same window via System Events)
	try
		tell application "System Events"
			tell process "Terminal"
				keystroke "t" using command down
			end tell
		end tell
		delay 0.4
		do script frontendCmd in backendWindow
	on error
		-- Fallback if Accessibility permission not granted: open a second window
		do script frontendCmd
	end try
end tell
