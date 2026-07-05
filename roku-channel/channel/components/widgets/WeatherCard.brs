sub init()
    m.icon = m.top.findNode("icon")
    m.temp = m.top.findNode("temp")
    m.condition = m.top.findNode("condition")
    m.hilo = m.top.findNode("hilo")
    m.summary = m.top.findNode("summary")
    m.footer = m.top.findNode("footer")
    m.top.visible = false   ' stay hidden until the first weather cache arrives
end sub

' Bound to the `weather` interface field. HomeHub pushes state.weather here; the block is omitted
' by /api/state until scripts/weather-refresh.py has written a cache, so guard for the empty case.
sub onWeather()
    w = m.top.weather
    if w = invalid or w.temp_c = invalid then
        m.top.visible = false
        return
    end if
    m.top.visible = true

    m.temp.text = snFmtInt(w.temp_c) + "°"
    m.condition.text = wxStr(w.condition)
    m.hilo.text = "H " + wxDeg(w.high_c) + "    L " + wxDeg(w.low_c)
    m.summary.text = wxStr(w.summary)

    ic = w.icon
    if ic <> invalid and ic <> "" then
        m.icon.uri = "pkg:/images/wx/" + ic + ".png"   ' EC iconCode -> local glyph
    else
        m.icon.uri = "pkg:/images/transparent.png"     ' empty code (EC leaves it blank) -> no glyph
    end if

    foot = wxStr(w.location)
    if w.observed_hm <> invalid and w.observed_hm <> "" then
        if foot <> "" then foot = foot + "  ·  "
        foot = foot + "updated " + wxStr(w.observed_hm)
    end if
    stale = (w.stale = true)
    if stale then foot = foot + "  ·  stale"
    m.footer.text = foot

    ' Dim the whole card when the cache is stale (dead-zone / last-good), so it reads as
    ' "last known" rather than current.
    if stale then
        m.top.opacity = 0.55
    else
        m.top.opacity = 1.0
    end if
end sub

' EC integer temp -> "23°"; invalid -> "--".
function wxDeg(v as dynamic) as string
    if v = invalid then return "--"
    return snFmtInt(v) + "°"
end function

' assoc value -> string; invalid -> "".
function wxStr(v as dynamic) as string
    if v = invalid then return ""
    return v.toStr()
end function
