' MainScene — route stack, mode controller, /api/state poll heartbeat.

sub init()
    m.splash = m.top.findNode("splash")
    m.home = m.top.findNode("home")
    m.drive = m.top.findNode("drive")
    m.toast = m.top.findNode("toast")
    m.toastBg = m.top.findNode("toastBg")
    m.poll = m.top.findNode("poll")
    m.stateTimer = m.top.findNode("stateTimer")
    m.splashTimer = m.top.findNode("splashTimer")
    m.toastTimer = m.top.findNode("toastTimer")

    m.route = "splash"
    m.haveState = false
    m.splashElapsed = false
    m.lastMode = ""
    m.modeStable = 0
    m.lastState = invalid

    m.poll.observeField("snapshot", "onPollState")
    m.stateTimer.observeField("fire", "onStateTick")
    m.splashTimer.observeField("fire", "onSplashElapsed")
    m.toastTimer.observeField("fire", "onToastHide")
    m.home.observeField("selectedRoute", "onHomeSelect")

    ' Fast-paint from cached state.
    cached = readCachedState()
    if cached <> invalid then
        m.haveState = true
        routeState(cached)
    end if

    m.poll.control = "RUN"
    m.stateTimer.control = "start"
    m.splashTimer.control = "start"

    slEvent("init", { route: m.route, api: snApiBase() })
end sub

sub onStateTick()
    m.poll.control = "RUN"
end sub

sub onSplashElapsed()
    m.splashElapsed = true
    maybeLeaveSplash()
end sub

sub onPollState()
    s = m.poll.snapshot
    if s = invalid then return
    if s.err <> invalid then
        slEvent("poll_error", { e: asStr(s.err) })
        return
    end if
    if m.dbgPoll = invalid then
        m.dbgPoll = true
        slEvent("poll_ok", { t: type(s), mode: asStr(s.mode) })
    end if
    m.haveState = true
    writeCachedState(s)
    routeState(s)
    maybeLeaveSplash()
end sub

sub routeState(s as object)
    m.lastState = s
    m.home.state = s
    m.drive.state = s
    applyMode(s)
end sub

sub maybeLeaveSplash()
    if m.route <> "splash" then return
    if not m.haveState then return
    if not m.splashElapsed then return
    target = routeForMode(modeOf(m.lastState))
    if target = "" then target = "home"
    go(target)
end sub

function modeOf(s as object) as string
    if s = invalid then return "unknown"
    if s.mode = invalid then return "unknown"
    return s.mode
end function

sub applyMode(s as object)
    mode = modeOf(s)
    if mode = m.lastMode then
        m.modeStable = m.modeStable + 1
    else
        m.lastMode = mode
        m.modeStable = 1
    end if
    if m.route = "splash" then return
    if not isPassive(m.route) then return
    if m.modeStable < 2 then return
    target = routeForMode(mode)
    if target <> "" and target <> m.route then
        slEvent("mode_switch", { mode: mode, to: target })
        go(target)
    end if
end sub

function routeForMode(mode as string) as string
    if mode = "driving" then return "drive"
    if mode = "at_home" then return "home"
    if mode = "parked" then return "home"   ' Camp screen arrives in P2
    return ""
end function

function isPassive(route as string) as boolean
    return route = "home" or route = "drive"
end function

sub go(route as string)
    m.splash.visible = (route = "splash")
    m.home.visible = (route = "home")
    m.drive.visible = (route = "drive")
    m.route = route
    if route = "home" then
        m.home.setFocus(true)
    else if route = "drive" then
        m.drive.setFocus(true)
    end if
    slEvent("route", { to: route })
end sub

sub onHomeSelect()
    r = m.home.selectedRoute
    if r = invalid or r = "" then return
    if Left(r, 6) = "toast:" then
        showToast(Mid(r, 7) + " - coming soon")
        return
    end if
    if r = "drive" then
        go("drive")
    else
        showToast(r + " - coming soon")
    end if
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "back" then
        if m.route <> "home" then
            go("home")
            return true
        end if
    end if
    return false
end function

sub showToast(text as string)
    m.toast.text = text
    m.toast.visible = true
    m.toastBg.visible = true
    m.toastTimer.control = "stop"
    m.toastTimer.control = "start"
end sub

sub onToastHide()
    m.toast.visible = false
    m.toastBg.visible = false
end sub

' --- cached state (registry, fast cold-start) ---
function readCachedState() as object
    raw = regRead(SN_REG_LAST_STATE())
    if raw = "" then return invalid
    return ParseJson(raw)
end function

sub writeCachedState(s as object)
    regWrite(SN_REG_LAST_STATE(), FormatJson(s))
end sub

' --- deep-link args (?apiBase=...&route=...) ---
sub onArgs()
    args = m.top.args
    if args = invalid then return
    if args.apiBase <> invalid and args.apiBase <> "" then
        regWrite(SN_REG_API_BASE(), args.apiBase)
        slEvent("apiBase_set", { apiBase: args.apiBase })
        m.poll.control = "RUN"
    end if
    if args.route <> invalid and args.route <> "" then
        go(args.route)
    end if
end sub
