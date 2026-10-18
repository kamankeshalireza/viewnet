from .selectors import get_category_tree


def nav_categories(request):
    return {"nav_categories": get_category_tree()}
