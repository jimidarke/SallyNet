sub init()
    m.rows = m.top.findNode("rows")
    m.detail = m.top.findNode("detail")
    m.empty = m.top.findNode("empty")
    m.clock = m.top.findNode("clock")

    m.rows.observeField("rowItemSelected", "onItemSelected")
    m.rows.observeField("rowItemFocused", "onItemFocused")
    m.clock.text = snClockHM()
end sub

sub onCatalog()
    cat = m.top.videoCatalog
    if cat = invalid then return
    m.rows.content = cat
    hasRows = (cat.getChildCount() > 0)
    m.empty.visible = not hasRows
    m.rows.visible = hasRows
    if hasRows then
        m.rows.jumpToRowItem = [0, 0]
        updateDetail(0, 0)
    end if
end sub

' RowList drives D-pad internally; we only react to focus/selection.
sub onItemFocused()
    fi = m.rows.rowItemFocused
    if fi <> invalid and fi.count() = 2 then updateDetail(fi[0], fi[1])
end sub

sub onItemSelected()
    si = m.rows.rowItemSelected
    if si = invalid or si.count() <> 2 then return
    n = itemNode(si[0], si[1])
    if n = invalid then return
    m.top.selectedItem = snItemAssocFromNode(n)
end sub

function itemNode(rowIdx as integer, colIdx as integer) as object
    cat = m.top.videoCatalog
    if cat = invalid then return invalid
    if rowIdx < 0 or rowIdx >= cat.getChildCount() then return invalid
    row = cat.getChild(rowIdx)
    if row = invalid or colIdx < 0 or colIdx >= row.getChildCount() then return invalid
    return row.getChild(colIdx)
end function

sub updateDetail(rowIdx as integer, colIdx as integer)
    n = itemNode(rowIdx, colIdx)
    if n = invalid then
        m.detail.text = ""
        return
    end if
    parts = []
    if n.title <> invalid and n.title <> "" then parts.push(n.title)
    if n.shortDescriptionLine1 <> invalid and n.shortDescriptionLine1 <> "" then parts.push(n.shortDescriptionLine1)
    if n.shortDescriptionLine2 <> invalid and n.shortDescriptionLine2 <> "" then parts.push(n.shortDescriptionLine2)
    if n.length <> invalid and n.length > 0 then parts.push(snFmtInt(n.length) + " s")
    m.detail.text = parts.join("    |    ")
end sub
