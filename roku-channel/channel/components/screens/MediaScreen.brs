sub init()
    m.tabRow = m.top.findNode("tabRow")
    m.moviesPane = m.top.findNode("moviesPane")
    m.tvPane = m.top.findNode("tvPane")
    m.tabMovies = m.top.findNode("tabMovies")
    m.tabMoviesStripeRed = m.top.findNode("tabMoviesStripeRed")
    m.tabMoviesStripeOrange = m.top.findNode("tabMoviesStripeOrange")
    m.tabTv = m.top.findNode("tabTv")
    m.tabTvStripeRed = m.top.findNode("tabTvStripeRed")
    m.tabTvStripeOrange = m.top.findNode("tabTvStripeOrange")

    m.moviesRows = m.top.findNode("moviesRows")
    m.tvRows = m.top.findNode("tvRows")
    m.tvEmpty = m.top.findNode("tvEmpty")
    m.detail = m.top.findNode("detail")
    m.clock = m.top.findNode("clock")

    m.moviesRows.observeField("rowItemSelected", "onMoviesItemSelected")
    m.moviesRows.observeField("rowItemFocused", "onMoviesItemFocused")
    m.tvRows.observeField("rowItemSelected", "onTvItemSelected")
    m.tvRows.observeField("rowItemFocused", "onTvItemFocused")
    m.clock.text = snClockHM()

    m.serverCatalog = invalid    ' raw movie catalog from the server (StudioListTask)
    m.displayCatalog = invalid   ' what moviesRows actually shows (Continue Watching + server rows)
    m.tvHasContent = false
    m.activeTab = 0     ' always Movies on open
    m.onTabRow = false
    updateTabVisuals()
end sub

sub onVisibleChange()
    if m.top.visible <> true then return
    ' initialFocus="moviesRows" always re-focuses the active pane's list on (re-)entry; keep
    ' our own tab-row-focus bookkeeping (and its stripe indicator) in sync with that.
    m.onTabRow = false
    m.clock.text = snClockHM()
    updateTabVisuals()
    ' Rebuild so Continue Watching reflects any movie just watched (bookmarks changed).
    rebuildMovies()
end sub

' Movies: RowList fed by movieCatalog (curated category rows). No empty-state toggle —
' the studio library has real content today.
sub onMovieCatalog()
    m.serverCatalog = m.top.movieCatalog
    rebuildMovies()
end sub

' Compose the displayed movie catalog: a Roku-side "Continue Watching" row (built from
' resume bookmarks in the registry — the server can't know per-device playback state)
' prepended to the server's curated rows.
sub rebuildMovies()
    if m.serverCatalog = invalid then return
    combined = m.serverCatalog.clone(true)
    cw = continueWatchingRow(m.serverCatalog)
    if cw <> invalid then combined.insertChild(cw, 0)
    m.displayCatalog = combined
    m.moviesRows.content = combined
end sub

function continueWatchingRow(catalog as object) as object
    row = invalid
    seen = {}
    for each srow in catalog.getChildren(-1, 0)
        for each item in srow.getChildren(-1, 0)
            id = item.id
            if id <> invalid and id <> "" and not seen.doesExist(id) then
                if bookmarkSeconds(id) > 0 then
                    if row = invalid then
                        row = createObject("roSGNode", "ContentNode")
                        row.title = "Continue Watching"
                    end if
                    row.appendChild(item.clone(true))
                    seen[id] = true
                end if
            end if
        end for
    end for
    return row
end function

function bookmarkSeconds(id as string) as integer
    v = regRead(SN_REG_RESUME_PREFIX() + id)
    if v = "" then return 0
    return v.toInt()
end function

' RowList drives D-pad internally; we only react to focus/selection.
sub onMoviesItemFocused()
    fi = m.moviesRows.rowItemFocused
    if fi <> invalid and fi.count() = 2 then updateDetail(m.displayCatalog, fi[0], fi[1])
end sub

sub onMoviesItemSelected()
    si = m.moviesRows.rowItemSelected
    if si = invalid or si.count() <> 2 then return
    n = itemNode(m.displayCatalog, si[0], si[1])
    if n = invalid then return
    m.top.selectedItem = snItemAssocFromNode(n)
end sub

' TV: rows of show cards. A card carries a detailUrl (not a playable url) -> selecting it
' publishes selectedShow so MainScene drills into EpisodesScreen (not VodPlayer).
sub onTvCatalog()
    cat = m.top.tvCatalog
    if cat = invalid then return
    m.tvRows.content = cat
    m.tvHasContent = (cat.getChildCount() > 0)
    m.tvEmpty.visible = not m.tvHasContent
    m.tvRows.visible = m.tvHasContent
end sub

sub onTvItemFocused()
    fi = m.tvRows.rowItemFocused
    if fi <> invalid and fi.count() = 2 then updateDetail(m.top.tvCatalog, fi[0], fi[1])
end sub

sub onTvItemSelected()
    si = m.tvRows.rowItemSelected
    if si = invalid or si.count() <> 2 then return
    n = itemNode(m.top.tvCatalog, si[0], si[1])
    if n = invalid then return
    m.top.selectedShow = { showId: n.id, title: n.title, detailUrl: n.detailUrl }
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

' --- tab strip (Movies | TV) -------------------------------------------------
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
        if m.activeTab < 1 then setActiveTab(m.activeTab + 1)
        return true
    else if key = "down" or key = "OK" then
        ' Only release the tab row if the active pane actually has focusable content
        ' (the TV pane is an empty placeholder until Phase 3) — avoids a focus trap.
        if focusActivePane() then
            m.onTabRow = false
            updateTabVisuals()
        end if
        return true
    end if
    return false
end function

sub setActiveTab(idx as integer)
    m.activeTab = idx
    m.moviesPane.visible = (idx = 0)
    m.tvPane.visible = (idx = 1)
    updateTabVisuals()
end sub

function focusActivePane() as boolean
    if m.activeTab = 0 then
        m.moviesRows.setFocus(true)
        return true
    end if
    if m.activeTab = 1 and m.tvHasContent then
        m.tvRows.setFocus(true)
        return true
    end if
    ' empty TV pane -> keep focus on the tab row (no focus trap).
    return false
end function

sub updateTabVisuals()
    setTabVisual(m.tabMovies, m.tabMoviesStripeRed, m.tabMoviesStripeOrange, 0)
    setTabVisual(m.tabTv, m.tabTvStripeRed, m.tabTvStripeOrange, 1)
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
