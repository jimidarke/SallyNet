' MainScene — route stack, mode controller, /api/state poll heartbeat.

sub init()
    m.splash = m.top.findNode("splash")
    m.home = m.top.findNode("home")
    m.drive = m.top.findNode("drive")
    m.camp = m.top.findNode("camp")
    m.map = m.top.findNode("map")
    m.media = m.top.findNode("media")
    m.vod = m.top.findNode("vod")
    m.photos = m.top.findNode("photos")
    m.qr = m.top.findNode("qr")
    m.list = m.top.findNode("mediaList")
    m.toast = m.top.findNode("toast")
    m.toastBg = m.top.findNode("toastBg")
    m.poll = m.top.findNode("poll")
    m.stateTimer = m.top.findNode("stateTimer")
    m.splashTimer = m.top.findNode("splashTimer")
    m.toastTimer = m.top.findNode("toastTimer")
    m.qrParent = "photos"

    m.route = "splash"
    m.haveState = false
    m.splashElapsed = false
    m.lastMode = ""
    m.modeStable = 0
    m.lastState = invalid
    m.manualRoute = false

    m.poll.observeField("snapshot", "onPollState")
    m.stateTimer.observeField("fire", "onStateTick")
    m.splashTimer.observeField("fire", "onSplashElapsed")
    m.toastTimer.observeField("fire", "onToastHide")
    m.home.observeField("selectedRoute", "onHomeSelect")

    ' media wiring
    m.media.observeField("selectedItem", "onMediaSelect")
    m.vod.observeField("requestBack", "onChildBack")
    m.photos.observeField("requestBack", "onChildBack")
    m.photos.observeField("requestQr", "onPhotosQr")
    m.qr.observeField("requestBack", "onChildBack")
    m.list.observeField("videoCatalog", "onVideoCatalog")
    m.list.observeField("photoCatalog", "onPhotoCatalog")
    m.list.control = "RUN"

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
    m.camp.state = s
    m.map.state = s
    applyMode(s)
end sub

sub maybeLeaveSplash()
    if m.route <> "splash" then return
    if not m.haveState then return
    if not m.splashElapsed then return
    target = routeForMode(modeOf(m.lastState))
    if target = "" then target = "home"
    goAuto(target)
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
    if target = "" or target = m.route then return
    ' Promoting into an active screen (drive/camp) is always allowed, but auto-routing
    ' must never demote a screen the user picked themselves back to the generic hub.
    if target = "home" and m.manualRoute then return
    slEvent("mode_switch", { mode: mode, to: target })
    goAuto(target)
end sub

function routeForMode(mode as string) as string
    if mode = "driving" then return "drive"
    if mode = "camping" then return "camp"
    if mode = "at_home" then return "home"
    if mode = "parked" then return "home"   ' generic stop -> hub
    return ""
end function

function isPassive(route as string) as boolean
    return route = "home" or route = "drive" or route = "camp"
end function

sub go(route as string)
    m.manualRoute = true
    applyRoute(route)
end sub

' Mode-triggered switch (applyMode) — kept distinct from go() so applyMode can tell
' "user picked this screen" from "auto-routing put me here" via m.manualRoute.
sub goAuto(route as string)
    m.manualRoute = false
    applyRoute(route)
end sub

sub applyRoute(route as string)
    ' Free the single H.264 decoder when leaving the player (decoder discipline).
    if m.route = "vod" and route <> "vod" then m.vod.active = false

    m.splash.visible = (route = "splash")
    m.home.visible = (route = "home")
    m.drive.visible = (route = "drive")
    m.camp.visible = (route = "camp")
    m.map.visible = (route = "map")
    m.media.visible = (route = "media")
    m.vod.visible = (route = "vod")
    m.photos.visible = (route = "photos")
    m.qr.visible = (route = "qr")
    m.route = route

    if route = "home" then
        m.home.setFocus(true)
    else if route = "drive" then
        m.drive.setFocus(true)
    else if route = "camp" then
        m.camp.setFocus(true)
    else if route = "map" then
        m.map.setFocus(true)
    else if route = "media" then
        m.media.setFocus(true)
    else if route = "photos" then
        m.photos.setFocus(true)
    else if route = "qr" then
        m.qr.setFocus(true)
    else if route = "vod" then
        m.vod.active = true   ' onActive -> startPlayback -> focuses the Video
    end if
    slEvent("route", { to: route })
end sub

' Back climbs the route stack: vod->media->home, photos->home, qr->photos.
function routeParent(route as string) as string
    if route = "vod" then return "media"
    if route = "media" then return "home"
    if route = "photos" then return "home"
    if route = "qr" then return m.qrParent
    if route = "drive" then return "home"
    if route = "camp" then return "home"
    if route = "map" then return "home"
    return "home"
end function

sub onHomeSelect()
    r = m.home.selectedRoute
    if r = invalid or r = "" then return
    if Left(r, 6) = "toast:" then
        showToast(Mid(r, 7) + " - coming soon")
        return
    end if
    if r = "drive" then
        go("drive")
    else if r = "camp" then
        go("camp")
    else if r = "map" then
        go("map")
    else if r = "media" then
        m.list.control = "RUN"
        go("media")
    else if r = "photos" then
        m.list.control = "RUN"
        go("photos")
    else
        showToast(r + " - coming soon")
    end if
end sub

sub onMediaSelect()
    it = m.media.selectedItem
    if it = invalid then return
    m.vod.item = it
    go("vod")
end sub

sub onPhotosQr()
    if m.photos.requestQr <> true then return
    m.qrParent = "photos"
    m.qr.refresh = true
    go("qr")
end sub

sub onChildBack()
    go(routeParent(m.route))
end sub

sub onVideoCatalog()
    m.media.videoCatalog = m.list.videoCatalog
end sub

sub onPhotoCatalog()
    m.photos.photoCatalog = m.list.photoCatalog
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "back" then
        if m.route = "home" or m.route = "splash" then return false
        go(routeParent(m.route))
        return true
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
