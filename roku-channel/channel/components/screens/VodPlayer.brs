' VodPlayer — progressive MP4 playback with trick play, resume bookmark, watchdog.

sub init()
    m.player = m.top.findNode("player")
    m.reconnectOverlay = m.top.findNode("reconnectOverlay")
    m.reconnectLabel = m.top.findNode("reconnectLabel")
    m.reconnectSub = m.top.findNode("reconnectSub")
    m.watchdog = m.top.findNode("watchdog")
    m.backoff = m.top.findNode("backoff")
    m.bookmarkTimer = m.top.findNode("bookmarkTimer")

    m.player.observeField("state", "onPlayerState")
    m.watchdog.observeField("fire", "onWatchdogTick")
    m.backoff.observeField("fire", "onBackoffElapsed")
    m.bookmarkTimer.observeField("fire", "onBookmarkTick")

    m.retry = 0
    m.lastPlaying = 0
    m.stopping = false
end sub

' --- public surface ---------------------------------------------------------
sub onItem()
    if m.top.active then startPlayback()
end sub

sub onActive()
    if m.top.active then
        startPlayback()
    else
        persistBookmark()
        m.stopping = true
        m.player.control = "stop"
        m.watchdog.control = "stop"
        m.bookmarkTimer.control = "stop"
    end if
end sub

' --- playback ---------------------------------------------------------------
sub startPlayback()
    it = m.top.item
    if it = invalid or it.url = invalid or it.url = "" then return

    c = createObject("roSGNode", "ContentNode")
    c.url = it.url
    c.streamFormat = "mp4"
    if it.title <> invalid then c.title = it.title
    len = 0
    if it.length <> invalid then
        len = snParseInt(it.length)
        c.length = len
    end if
    resume = bookmarkFor(currentId())
    if resume > 0 and (len = 0 or resume < (len - 10)) then c.playStart = resume

    m.player.content = c
    m.player.enableTrickPlay = true
    m.player.enableUI = true
    m.player.seekMode = "accurate"

    m.stopping = false
    m.retry = 0
    m.lastPlaying = snNowSeconds()
    hideReconnect()
    m.player.control = "play"
    m.player.setFocus(true)
    m.watchdog.control = "start"
    m.bookmarkTimer.control = "start"
    slEvent("vod_start", { id: currentId() })
end sub

sub onPlayerState()
    st = m.player.state
    if st = "playing" then
        m.lastPlaying = snNowSeconds()
        m.retry = 0
        hideReconnect()
    else if st = "finished" then
        ' Normal EOF for VOD — clear the bookmark and return to browse.
        clearBookmark(currentId())
        m.bookmarkTimer.control = "stop"
        slEvent("vod_finished", { id: currentId() })
        m.top.requestBack = true
    else if st = "error" then
        scheduleReconnect("error")
    else if st = "stopped" then
        ' Ignore our own intentional stops; an unexpected stop is treated as an error.
        if not m.stopping then scheduleReconnect("stopped")
    end if
end sub

sub onWatchdogTick()
    age = snNowSeconds() - m.lastPlaying
    if age > SN_VOD_WATCHDOG_S() and m.player.state <> "playing" then
        slEvent("vod_watchdog", { age: age, state: m.player.state })
        m.retry = 0
        m.stopping = true
        m.player.control = "stop"
        startPlayback()
    end if
end sub

sub onBackoffElapsed()
    startPlayback()
end sub

sub scheduleReconnect(reason as string)
    m.retry = m.retry + 1
    if m.retry > 4 then
        m.retry = 0
        showReconnect("Can't play this clip", "Press Back to return")
        return
    end if
    delay = snNextBackoffSeconds(m.retry)
    showReconnect("Playback error — retrying", "attempt " + m.retry.toStr() + " in " + delay.toStr() + "s")
    slEvent("vod_reconnect", { reason: reason, attempt: m.retry, delay: delay })
    m.stopping = true
    m.player.control = "stop"
    m.backoff.duration = delay
    m.backoff.control = "start"
end sub

' --- resume bookmark (registry, keyed on contentid) -------------------------
function currentId() as string
    it = m.top.item
    if it = invalid or it.contentid = invalid then return ""
    return it.contentid
end function

function bookmarkFor(cid as string) as integer
    if cid = "" then return 0
    v = regRead(SN_REG_RESUME_PREFIX() + cid)
    if v = "" then return 0
    return v.toInt()
end function

sub persistBookmark()
    cid = currentId()
    if cid = "" then return
    posSec = m.player.position
    if posSec = invalid then return
    regWrite(SN_REG_RESUME_PREFIX() + cid, Int(posSec).toStr())
end sub

sub clearBookmark(cid as string)
    if cid = "" then return
    regWrite(SN_REG_RESUME_PREFIX() + cid, "0")
end sub

sub onBookmarkTick()
    persistBookmark()
end sub

' --- overlay ----------------------------------------------------------------
sub showReconnect(headline as string, sub_ as string)
    m.reconnectOverlay.visible = true
    m.reconnectLabel.text = headline
    m.reconnectSub.text = sub_
end sub

sub hideReconnect()
    m.reconnectOverlay.visible = false
end sub

' --- input ------------------------------------------------------------------
' Video has focus, so its built-in trick-play UI consumes transport keys; Back
' bubbles up to here.
function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "back" then
        persistBookmark()
        m.top.requestBack = true
        return true
    end if
    return false
end function
