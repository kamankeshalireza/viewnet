import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError

from apps.catalog import selectors
from apps.catalog.models import Category

from .helpers import make_category

pytestmark = pytest.mark.django_db


def test_paths_and_slug_path_and_depth():
    root = make_category("قاب گوشی")
    child = make_category("قاب آیفون", parent=root)
    leaf = make_category("قاب آیفون ۱۵", parent=child)
    root.refresh_from_db(), child.refresh_from_db(), leaf.refresh_from_db()
    assert root.path == f"/{root.pk}/" and root.depth == 0 and root.slug_path == "قاب-گوشی"
    assert child.path == f"/{root.pk}/{child.pk}/" and child.slug_path == "قاب-گوشی/قاب-آیفون"
    assert leaf.depth == 2 and leaf.get_absolute_url() == f"/category/{leaf.slug_path}/"
    assert [c.pk for c in leaf.ancestors()] == [root.pk, child.pk]
    assert set(root.subtree_ids()) == {root.pk, child.pk, leaf.pk}


def test_zwnj_in_name_becomes_separator_in_slug():
    c = make_category("گوشی\u200cهای هوشمند")
    assert c.slug == "گوشی-های-هوشمند"


def test_moving_a_branch_repaths_the_subtree():
    a, b = make_category("الف"), make_category("ب")
    child = make_category("فرزند", parent=a)
    leaf = make_category("نوه", parent=child)
    child.parent = b
    child.save()
    leaf.refresh_from_db(), child.refresh_from_db()
    assert child.path == f"/{b.pk}/{child.pk}/" and child.slug_path == "ب/فرزند"
    assert leaf.path == f"/{b.pk}/{child.pk}/{leaf.pk}/" and leaf.slug_path == "ب/فرزند/نوه" and leaf.depth == 2


def test_renaming_changes_descendant_urls():
    root = make_category("قدیمی")
    child = make_category("زیر", parent=root)
    root.name, root.slug = "جدید", "جدید"
    root.save()
    child.refresh_from_db()
    assert child.slug_path == "جدید/زیر"


def test_cycle_is_rejected():
    root = make_category("ریشه")
    child = make_category("فرزند", parent=root)
    root.parent = child
    with pytest.raises(ValidationError):
        root.full_clean()
    root.parent = root
    with pytest.raises(ValidationError):
        root.clean()


def test_tree_is_cached_and_invalidated_on_change():
    root = make_category("ریشه")
    assert [n["name"] for n in selectors.get_category_tree()] == ["ریشه"]
    assert cache.get("catalog:category_tree:v1") is not None
    make_category("فرزند", parent=root)
    tree = selectors.get_category_tree()
    assert [c["name"] for c in tree[0]["children"]] == ["فرزند"]
    Category.objects.get(name="فرزند").delete()
    assert selectors.get_category_tree()[0]["children"] == []


def test_inactive_categories_hidden_from_tree():
    make_category("فعال")
    make_category("مخفی", is_active=False)
    assert [n["name"] for n in selectors.get_category_tree()] == ["فعال"]
