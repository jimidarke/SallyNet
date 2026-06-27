' MapScreen — fullscreen ambient map Poster, re-fetched each /api/state poll.
'
' The map PNG lives at a stable URL but its pixels change as Sally moves, and a Roku Poster
' caches by URI — so we cache-bust with the poll's `state.ts`. The server's render cache
' ignores the bust param, so each Roku fetch is fresh HTTP while the Pi still renders at most
' once every few seconds. Two posters ping-pong (lifted from PhotoGallery) so a slow or failed
' fetch never blanks the screen.

sub init()
    m.posterA = m.top.findNode("posterA")
    m.posterB = m.top.findNode("posterB")
    m.statusMsg = m.top.findNode("statusMsg")

    m.posterA.observeField("loadStatus", "onPosterLoaded")
    m.posterB.observeField("loadStatus", "onPosterLoaded")
    m.top.observeField("visible", "onVisible")

    m.showingA = true
    m.incoming = invalid
    m.curV = invalid        ' latest /api/state tick seen
    m.fetchedV = invalid    ' tick currently shown / loading
    m.everLoaded = false
end sub

sub onState()
    s = m.top.state
    if s = invalid then return
    if s.ts <> invalid then
        m.curV = s.ts.toStr()
    else
        m.curV = "0"
    end if
    maybeRefresh()
end sub

sub onVisible()
    if m.top.visible = true then maybeRefresh()
end sub

sub maybeRefresh()
    ' Only fetch while on-screen — no point spending LTE on a hidden map.
    if m.top.visible <> true then return
    if m.curV = invalid then return
    if m.curV = m.fetchedV then return     ' already showing this tick
    if m.incoming <> invalid then return    ' a load is already in flight
    m.fetchedV = m.curV
    if m.showingA then
        m.incoming = m.posterB
    else
        m.incoming = m.posterA
    end if
    m.incoming.uri = snMapUrl(1920, 1080, m.curV)
end sub

sub onPosterLoaded()
    if m.incoming = invalid then return
    st = m.incoming.loadStatus
    if st = "ready" then
        if m.showingA then
            m.posterB.opacity = 1.0
            m.posterA.opacity = 0.0
            m.showingA = false
        else
            m.posterA.opacity = 1.0
            m.posterB.opacity = 0.0
            m.showingA = true
        end if
        m.incoming = invalid
        m.everLoaded = true
        m.statusMsg.visible = false
    else if st = "failed" then
        ' Keep the current frame up; let the next poll retry this tick.
        m.incoming = invalid
        m.fetchedV = invalid
        if not m.everLoaded then
            m.statusMsg.text = "Waiting for map…"
            m.statusMsg.visible = true
        end if
    end if
end sub
