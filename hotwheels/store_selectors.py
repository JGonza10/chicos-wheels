# selectors.py

def get_selector(url: str):
    """
    Devuelve los selectores CSS correctos según la tienda detectada en la URL.
    Devuelve None si la tienda no está soportada.

    Selector de respaldo (2026-09-16): no hace falta una lista/mecanismo
    aparte — un selector CSS con comas ya es "cualquiera de estos" para
    Playwright (mira "sold_out" de Mattel abajo: 3 alternativas en un solo
    string). Si Mattel cambia el HTML del botón de compra, agrega la
    alternativa nueva separada por coma en "buy_button" en vez de tocar
    bot_logic.py — es lo mismo que ya se usa aquí para detectar agotado.
    """

    # Mattel Creations
    if "creations.mattel.com" in url:
        return {
            "store": "mattel",
            "buy_button": "button.product__add-to-cart",
            "sold_out": "span.product__status-badge:has-text('Sold Out'), button.product__add-to-cart.sold-out-btn, button.product__add-to-cart[disabled]",
            "cookie_consent": "#truste-consent-button",
            "popup_close": "button[aria-label='Close dialog']",
            "quantity_input": "input[name='quantity']",
            "quantity_increase": "button.js-qty-increment",
            "quantity_limit": "text=/reached the limit/i",
            # Botón real de "Checkout" en /cart (confirmado 2026-09-28): ir
            # directo a /checkout ya no funciona, hay que pasar por /cart y
            # darle clic a este botón para llegar al checkout de invitado real.
            "cart_checkout": "button.cart__checkout, button[name='checkout']",
            # Contador del carrito en el header: confirma que "Add to Bag"
            # realmente agregó el producto antes de navegar al carrito.
            "cart_count": "a.header__cart-count-wrapper"
        }

    # Amazon México
    elif "amazon.com.mx" in url:
        return {
            "store": "amazon_mx",
            "buy_button": "input#add-to-cart-button",
            "sold_out": "span#availability:has-text('Agotado')"
        }

    # Amazon US
    elif "amazon.com" in url:
        return {
            "store": "amazon_us",
            "buy_button": "input#add-to-cart-button",
            "sold_out": "span#availability:has-text('Currently unavailable')"
        }

    # Walmart México
    elif "walmart.com.mx" in url:
        return {
            "store": "walmart_mx",
            "buy_button": "button.prod-ProductCTA--primary",
            "sold_out": "span:has-text('Agotado')"
        }

    # Target US
    elif "target.com" in url:
        return {
            "store": "target_us",
            "buy_button": "button[data-test='addToCartButton']",
            "sold_out": "div[data-test='soldOutMessage']"
        }

    return None
