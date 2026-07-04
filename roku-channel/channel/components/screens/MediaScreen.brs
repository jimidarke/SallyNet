sub init()
    m.tabRow = m.top.findNode("tabRow")
    m.tripsPane = m.top.findNode("tripsPane")
    m.moviesPane = m.top.findNode("moviesPane")
    m.tvPane = m.top.findNode("tvPane")
    m.tabTrips = m.top.findNode("tabTrips")
    m.tabTripsStripeRed = m.top.findNode("tabTripsStripeRed")
    m.tabTripsStripeOrange = m.top.findNode("tabTripsStripeOrange")
    m.tabMovies = m.top.findNode("tabMovies")
    m.tabMoviesStripeRed = m.top.findNode("tabMoviesStripeRed")
    m.tabMoviesStripeOrange = m.top.findNode("tabMoviesStripeOrange")
    m.tabTv = m.top.findNode("tabTv")
    m.tabTvStripeRed = m.top.findNode("tabTvStripeRed")
    m.tabTvStripeOrange = m.top.findNode("tabTvStripeOrange")

    m.rows = m.top.findNode("rows")
    m.moviesRows = m.top.findNode("moviesRows")
    m.detail = m.top.findNode("detail")
    m.empty = m.top.findNode("empty")
    m.clock = m.top.findNode("clock")

    m.rows.observeField("rowItemSelected", "onItemSelected")
    m.rows.observeField("rowItemFocused", "onItemFocused")
    m.moviesRows.observeField("rowItemSelected", "onMoviesItemSelected")
    m.moviesRows.observeField("rowItemFocused", "onMoviesItemFocused")
    m.clock.text = snClockHM()

    m.activeTab = 0     ' always Trips on open
    m.onTabRow = false
    updateTabVisuals()
end sub

sub onVisibleChange()
    if m.top.visible <> true then return
    ' initialFocus="rows" always re-focuses the active pane's list on (re-)entry; keep our
    ' own tab-row-focus bookkeeping (and its stripe indicator) in sync with that.
    m.onTabRow = false
    updateTabVisuals()
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
        updateDetail(cat, 0, 0)
    end if
end sub

' Movies: same RowList mechanism as Trips, fed by a second catalog field. No empty-state
' toggle — the studio library already has real content today.
sub onMovieCatalog()
    cat = m.top.movieCatalog
    if cat = invalid then return
    m.moviesRows.content = cat
end sub

' RowList drives D-pad internally; we only react to focus/selection.
sub onItemFocused()
    fi = m.rows.rowItemFocused
    if fi <> invalid and fi.count() = 2 then updateDetail(m.top.videoCatalog, fi[0], fi[1])
end sub

sub onItemSelected()
    si = m.rows.rowItemSelected
    if si = invalid or si.count() <> 2 then return
    n = itemNode(m.top.videoCatalog, si[0], si[1])
    if n = invalid then return
    m.top.selectedItem = snItemAssocFromNode(n)
end sub

sub onMoviesItemFocused()
    fi = m.moviesRows.rowItemFocused
    if fi <> invalid and fi.count() = 2 then updateDetail(m.top.movieCatalog, fi[0], fi[1])
end sub

sub onMoviesItemSelected()
    si = m.moviesRows.rowItemSelected
    if si = invalid or si.count() <> 2 then return
    n = itemNode(m.top.movieCatalog, si[0], si[1])
    if n = invalid then return
    m.top.selectedItem = snItemAssocFromNode(n)
end sub

function itemNode(cat as object, rowIdx as integer, colIdx as integer) as object
    if cat = invalid then return invalid
    if rowIdx < 0 or rowIdx >= cat.getChildCount() then return invalid
    row = cat.getChild(rowIdx)
    if row = invalid or colIdx < 0 or colIdx >= row.getChildCount() then return invalid
    return row.getChild(colIdx)
end function

sub updateDetail(cat as object, rowIdx as integer, colIdx as integer)
    n = itemNode(cat, rowIdx, colIdx)
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

' --- tab strip ---------------------------------------------------------------
' Up from a pane moves real SceneGraph focus onto the inert tabRow Group (so the
' RowList genuinely releases D-pad input); Left/Right then switches the active pane;
' Down/OK returns focus to it. tabRow has no script of its own, so while it holds
' focus every key not handled below bubbles no further than this function.

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if not m.onTabRow then
        if key = "up" then
            m.onTabRow = true
            m.tabRow.setFocus(true)
            updateTabVisuals()
            return true
        end if
        return false
    end if
    if key = "left" then
        if m.activeTab > 0 then setActiveTab(m.activeTab - 1)
        return true
    else if key = "right" then
        if m.activeTab < 2 then setActiveTab(m.activeTab + 1)
        return true
    else if key = "down" or key = "OK" then
        m.onTabRow = false
        updateTabVisuals()
        focusActivePane()
        return true
    end if
    return false
end function

sub setActiveTab(idx as integer)
    m.activeTab = idx
    m.tripsPane.visible = (idx = 0)
    m.moviesPane.visible = (idx = 1)
    m.tvPane.visible = (idx = 2)
    updateTabVisuals()
end sub

sub focusActivePane()
    if m.activeTab = 0 then
        m.rows.setFocus(true)
    else if m.activeTab = 1 then
        m.moviesRows.setFocus(true)
    end if
    ' tvPane has no focusable content yet (later phase).
end sub

sub updateTabVisuals()
    setTabVisual(m.tabTrips, m.tabTripsStripeRed, m.tabTripsStripeOrange, 0)
    setTabVisual(m.tabMovies, m.tabMoviesStripeRed, m.tabMoviesStripeOrange, 1)
    setTabVisual(m.tabTv, m.tabTvStripeRed, m.tabTvStripeOrange, 2)
end sub

sub setTabVisual(lbl as object, stripeRed as object, stripeOrange as object, idx as integer)
    active = (idx = m.activeTab)
    if active then
        lbl.color = SN_INK()
    else
        lbl.color = SN_MUTED()
    end if
    showStripe = active and m.onTabRow
    stripeRed.visible = showStripe
    stripeOrange.visible = showStripe
end sub
