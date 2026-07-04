' StudioListTask — fetch /api/media?type=movies, then each category's items. Builds the
' movieCatalog node tree (rows = categories, items = that category's movies). One-shot per
' control="RUN", same shape as MediaListTask's trips fetch.

sub init()
    m.top.functionName = "runFetch"
end sub

sub runFetch()
    root = createObject("roSGNode", "ContentNode")

    movies = httpGetJson(snMediaMoviesUrl())
    if movies <> invalid and movies.collections <> invalid then
        for each c in movies.collections
            durl = snCollectionUrl("")
            if c.detailUrl <> invalid then
                durl = snApiBase() + c.detailUrl
            else if c.id <> invalid then
                durl = snCollectionUrl(c.id)
            end if
            detail = httpGetJson(durl)
            if detail <> invalid and detail.items <> invalid then
                row = invalid
                for each it in detail.items
                    if it.type = "video" and it.url <> invalid then
                        if row = invalid then
                            row = root.createChild("ContentNode")
                            row.title = c.title
                        end if
                        n = row.createChild("ContentNode")
                        if it.title <> invalid then n.title = it.title
                        n.hdPosterUrl = snMediaItemUrl(it.poster)
                        if it.year <> invalid then n.shortDescriptionLine1 = it.year
                        n.url = snMediaItemUrl(it.url)
                        n.streamFormat = "mp4"
                        if it.durationSec <> invalid then n.length = snParseInt(it.durationSec)
                        if it.id <> invalid then n.id = it.id
                        if it.kidSafe <> invalid then n.kidSafe = it.kidSafe
                    end if
                end for
            end if
        end for
    end if
    m.top.movieCatalog = root

    m.top.ok = true
    slEvent("movie_catalog", { rows: root.getChildCount() })
end sub
