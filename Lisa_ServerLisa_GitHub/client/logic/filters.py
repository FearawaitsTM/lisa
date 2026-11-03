def filter_summaries(summaries, query="", employee_type="все"):
    query = str(query or "").strip().lower()
    employee_type = employee_type or "все"
    result = []
    for item in summaries:
        if query and query not in str(item.get("employee_name", "")).lower():
            continue
        if employee_type != "все" and item.get("employee_type") != employee_type:
            continue
        result.append(item)
    return result
