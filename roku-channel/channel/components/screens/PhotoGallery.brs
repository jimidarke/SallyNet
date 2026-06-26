sub init()
    m.posterA = m.top.findNode("posterA")
    m.posterB = m.top.findNode("posterB")
    m.metaScrim = m.top.findNode("metaScrim")
    m.metaDate = m.top.findNode("metaDate")
    m.metaSub = m.top.findNode("metaSub")
    m.counter = m.top.findNode("counter")
    m.empty = m.top.findNode("empty")
    m.autoAdvance = m.top.findNode("autoAdvance")

    m.posterA.observeField("loadStatus", "onPosterLoaded")
    m.posterB.observeField("loadStatus", "onPosterLoaded")
    m.autoAdvance.observeField("fire", "onAutoAdvance")

    m.items = []
    m.idx = 0
    m.pending = 0
    m.showingA = true
    m.incoming = invalid
    m.playing = true
end sub

sub onCatalog()
    cat = m.top.photoCatalog
    if cat = invalid or cat.photos = invalid then return
    m.items = cat.photos
    has = (m.items.count() > 0)
    m.empty.visible = not has
    m.metaScrim.visible = has
    if has then
        m.idx = 0
        showIndex(0)
        startAuto()
    else
        m.autoAdvance.control = "stop"
    end if
end sub

sub showIndex(i as integer)
    if i < 0 or i >= m.items.count() then return
    m.pending = i
    if m.showingA then
        m.incoming = m.posterB
    else
        m.incoming = m.posterA
    end if
    url = snMediaItemUrl(m.items[i].url)
    if url = "" then return
    m.incoming.uri = url
end sub

sub onPosterLoaded()
    if m.incoming = invalid then return
    if m.incoming.loadStatus = "ready" then
        if m.showingA then
            m.posterB.opacity = 1.0
            m.posterA.opacity = 0.0
            m.showingA = false
        else
            m.posterA.opacity = 1.0
            m.posterB.opacity = 0.0
            m.showingA = true
        end if
        m.idx = m.pending
        m.incoming = invalid
        updateMeta()
    else if m.incoming.loadStatus = "failed" then
        m.incoming = invalid   ' leave current image up; user/auto can move on
    end if
end sub

sub updateMeta()
    if m.idx < 0 or m.idx >= m.items.count() then return
    it = m.items[m.idx]
    m.metaDate.text = snDateLabelFromIso(it.captureDatetime)
    sub_ = ""
    if it.title <> invalid and it.title <> "" then sub_ = it.title
    m.metaSub.text = sub_
    m.counter.text = (m.idx + 1).toStr() + " / " + m.items.count().toStr()
end sub

sub startAuto()
    m.playing = true
    m.autoAdvance.control = "stop"
    m.autoAdvance.control = "start"
end sub

sub onAutoAdvance()
    nextPhoto()
end sub

sub nextPhoto()
    if m.items.count() = 0 then return
    showIndex((m.idx + 1) mod m.items.count())
end sub

sub prevPhoto()
    if m.items.count() = 0 then return
    p = m.idx - 1
    if p < 0 then p = m.items.count() - 1
    showIndex(p)
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "right" or key = "down" then
        nextPhoto()
        startAuto()
        return true
    else if key = "left" or key = "up" then
        prevPhoto()
        startAuto()
        return true
    else if key = "OK" then
        m.playing = not m.playing
        if m.playing then
            startAuto()
        else
            m.autoAdvance.control = "stop"
        end if
        return true
    else if key = "info" or key = "options" then
        m.top.requestQr = true
        return true
    else if key = "back" then
        m.autoAdvance.control = "stop"
        m.top.requestBack = true
        return true
    end if
    return false
end function
