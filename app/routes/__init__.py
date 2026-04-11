def paginate_query(query, page=1, per_page=25, max_per_page=100):
    """Apply pagination to a SQLAlchemy query. Returns (items, pagination_info)."""
    page = max(1, page)
    per_page = min(max(1, per_page), max_per_page)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return items, {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }
