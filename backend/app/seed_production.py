# — demonstracijski izdelek z recepturo.
"""Ročna priprava demonstracijskega izdelka in recepture; brez nalogov ali porabe."""
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Material, MaterialType, Product, Recipe, RecipeItem


def main():
    with SessionLocal() as db:
        product = db.scalar(select(Product).where(Product.sku == "SOK-JAB-1L"))
        if product is None:
            product = Product(name="Jabolčni sok 1 L", sku="SOK-JAB-1L", unit="kos")
            db.add(product)
            db.flush()
        if db.scalar(select(Recipe.id).where(Recipe.product_id == product.id, Recipe.active.is_(True))) is not None:
            print("Izdelek že ima aktivno recepturo; podatki niso bili spremenjeni.")
            return
        ingredients = []
        for name, material_type, unit, quantity in (
            ("Jabolčni koncentrat", MaterialType.ingredient, "kg", "80"),
            ("Sladkor", MaterialType.ingredient, "kg", "25"),
            ("Plastenka 1 L", MaterialType.packaging, "kos", "1000"),
        ):
            material = db.scalar(select(Material).where(
                Material.name == name, Material.type == material_type, Material.unit == unit,
            ).order_by(Material.id))
            if material is None:
                material = Material(name=name, type=material_type, unit=unit)
                db.add(material)
                db.flush()
            ingredients.append((material, Decimal(quantity)))
        previous = db.scalar(select(func.max(Recipe.version)).where(Recipe.product_id == product.id)) or 0
        recipe = Recipe(product_id=product.id, version=previous + 1, output_qty=Decimal("1000"), active=True)
        db.add(recipe)
        db.flush()
        db.add_all([RecipeItem(recipe_id=recipe.id, material_id=material.id, qty=qty) for material, qty in ingredients])
        db.commit()
    print("Demonstracijski izdelek in receptura sta pripravljena.")


if __name__ == "__main__":
    main()
