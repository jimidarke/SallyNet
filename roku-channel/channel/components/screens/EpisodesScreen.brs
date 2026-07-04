sub init()
    m.epRows = m.top.findNode("epRows")
    m.empty = m.top.findNode("empty")
    m.detail = m.top.findNode("detail")
    m.clock = m.top.findNode("clock")
    m.showTitleLbl = m.top.findNode("showTitle")
    m.task = m.top.findNode("detailTask")

    m.epRows.observeField("rowItemSelected", "onEpisodeSelected")
    m.epRows.observeField("rowItemFocused", "onEpisodeFocused")
    m.task.observeField("ok", "onDetail")
end sub

sub onShow()
    s = m.top.show
    if s = invalid then return
    m.clock.text = snClockHM()
    m.showTitleLbl.text = ""
    if s.title <> invalid then m.showTitleLbl.text = s.title
    m.empty.visible = false
    if s.detailUrl <> invalid and s.detailUrl <> "" then
        m.task.showUrl = s.detailUrl
        m.task.control = "RUN"
    end if
end sub

sub onDetail()
    if m.task.ok <> true then return
    if m.task.showTitle <> invalid and m.task.showTitle <> "" then m.showTitleLbl.text = m.task.showTitle
    cat = m.task.showDetail
    m.epRows.content = cat
    has = (cat <> invalid and cat.getChildCount() > 0)
    m.empty.visible = not has
    m.epRows.visible = has
    if has then
        m.epRows.setFocus(true)
        m.epRows.jumpToRowItem = [0, 0]
        updateDetail(0, 0)
    end if
end sub

' RowList drives D-pad internally; we only react to focus/selection.
sub onEpisodeFocused()
    fi = m.epRows.rowItemFocused
    if fi <> invalid and fi.count() = 2 then updateDetail(fi[0], fi[1])
end sub

sub onEpisodeSelected()
    si = m.epRows.rowItemSelected
    if si = invalid or si.count() <> 2 then return
    idx = flatIndex(si[0], si[1])
    flat = m.task.episodesFlat
    if flat = invalid or idx < 0 or idx >= flat.count() then return
    ' Hand VodPlayer the whole show as a play queue, starting at the picked episode.
    m.top.selectedEpisode = { queue: flat, index: idx }
end sub

' (row, col) -> index into episodesFlat: sum of prior seasons' episode counts + col.
function flatIndex(rowIdx as integer, colIdx as integer) as integer
    cat = m.task.showDetail
    if cat = invalid then return -1
    idx = 0
    for r = 0 to rowIdx - 1
        row = cat.getChild(r)
        if row <> invalid then idx = idx + row.getChildCount()
    end for
    return idx + colIdx
end function

sub updateDetail(rowIdx as integer, colIdx as integer)
    cat = m.task.showDetail
    if cat = invalid then return
    row = cat.getChild(rowIdx)
    if row = invalid then return
    n = row.getChild(colIdx)
    if n = invalid then
        m.detail.text = ""
        return
    end if
    parts = []
    if n.title <> invalid and n.title <> "" then parts.push(n.title)
    if n.length <> invalid and n.length > 0 then parts.push(snFmtInt(n.length) + " s")
    m.detail.text = parts.join("    |    ")
end sub
