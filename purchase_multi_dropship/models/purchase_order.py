"""Purchase order extension: allocate purchased quantities to customers."""

from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class PurchaseOrder(models.Model):
    """Allocate a purchase to customers, then sell and dropship their shares.

    Allocated quantities leave the vendor directly for each customer through
    a dropship; the purchase order's receipt keeps only the unallocated rest.
    """

    _inherit = "purchase.order"

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    allocation_ids = fields.One2many(
        "purchase.order.allocation", "order_id",
        string="Customer Allocations", copy=False,
    )
    # Products on the order; used to limit the products offered in allocations.
    allocation_product_ids = fields.Many2many(
        "product.product", compute="_compute_allocation_product_ids"
    )
    sale_order_ids = fields.One2many(
        "sale.order", "source_purchase_id", string="Customer Orders"
    )
    sale_order_count = fields.Integer(compute="_compute_sale_order_count")

    # Drive the visibility of the Generate button and the Allocations tab.
    has_pending_allocations = fields.Boolean(compute="_compute_allocation_status")
    can_allocate = fields.Boolean(compute="_compute_allocation_status")    

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    @api.depends("order_line.product_id")
    def _compute_allocation_product_ids(self):
        """List the products purchased on the order."""
        for order in self:
            order.allocation_product_ids = order.order_line.product_id

    @api.depends("sale_order_ids")
    def _compute_sale_order_count(self):
        """Count the customer orders generated from this purchase."""
        for order in self:
            order.sale_order_count = len(order.sale_order_ids)


    @api.depends(
        "state",
        "order_line.product_qty",
        "order_line.move_ids.state",
        "order_line.move_ids.product_uom_qty",
        "allocation_ids.product_qty",
        "allocation_ids.sale_line_id",
    )
    @api.depends(
        "state",
        "order_line.move_ids.state",
        "order_line.move_ids.product_uom_qty",
        "allocation_ids.sale_line_id",
    )
    def _compute_allocation_status(self):
        """Flag allocations waiting for generation, and goods still to receive.

        Allocation is possible on confirmed orders while something is still
        waiting on the receipt: ordered = dropshipped + received.
        """
        for order in self:
            order.has_pending_allocations = bool(
                order.allocation_ids.filtered(lambda a: not a.sale_line_id)
            )
            order.can_allocate = order.state in ("purchase", "done") and any(
                float_compare(quantity, 0.0, precision_rounding=product.uom_id.rounding) > 0
                for product, quantity in order._get_open_receipt_quantities().items()
            )

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_generate_customer_orders(self):
        """Sell and dropship every new allocation, one order per customer."""
        for order in self:
            if order.state not in ("purchase", "done"):
                raise UserError(_("Confirm the purchase order before generating customer orders."))
            pending = order.allocation_ids.filtered(lambda a: not a.sale_line_id)
            if not pending:
                raise UserError(_("%s has no new allocations to generate.", order.name))

            order._check_open_receipt_quantities(pending)
            order._reduce_receipt(pending)
            for customer, allocations in pending.grouped("partner_id").items():
                sale_order = order._create_customer_sale_order(customer, allocations)
                sale_order.action_confirm()
                order._create_customer_dropship(sale_order, allocations)
        return True

    def action_view_customer_orders(self):
        """Open the sales orders generated from this purchase."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sale.action_orders")
        action["domain"] = [("source_purchase_id", "=", self.id)]
        action["context"] = {"create": False}
        return action

    # -------------------------------------------------------------------------
    # Sales orders
    # -------------------------------------------------------------------------

    def _create_customer_sale_order(self, customer, allocations):
        """Create one customer's sales order and link each allocation to its line.

        Sale prices are entered in the purchase order's currency and converted
        to the sales order's currency when they differ.
        """
        self.ensure_one()
        sale_order = self.env["sale.order"].create({
            "partner_id": customer.id,
            "company_id": self.company_id.id,
            "origin": self.name,
            "source_purchase_id": self.id,
        })
        sale_order.order_line = [
            Command.create({
                "product_id": allocation.product_id.id,
                "product_uom_qty": allocation.product_qty,
                "product_uom": allocation.product_uom_id.id,
                "price_unit": self.currency_id._convert(
                    allocation.price_unit, sale_order.currency_id,
                    self.company_id, fields.Date.context_today(self),
                ),
            })
            for allocation in allocations
        ]
        # Lines are created in the same order as the allocations.
        for allocation, line in zip(allocations, sale_order.order_line):
            allocation.sale_line_id = line
        return sale_order

    # -------------------------------------------------------------------------
    # Dropships and receipt
    # -------------------------------------------------------------------------

    def _create_customer_dropship(self, sale_order, allocations):
        """Create and confirm the dropship of one customer's allocations.

        Each move is linked to the purchase line (received quantity and vendor
        billing), to the sales line (delivered quantity) and to the sales
        order's procurement group (the order's deliveries).
        """
        self.ensure_one()
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "dropship"), ("company_id", "=", self.company_id.id)], limit=1
        )
        if not picking_type:
            raise UserError(_("No Dropship operation type exists for %s.", self.company_id.name))

        group = sale_order.procurement_group_id
        if not group:
            group = self.env["procurement.group"].create(
                sale_order.order_line[:1]._prepare_procurement_group_vals()
            )
            sale_order.procurement_group_id = group

        customer = sale_order.partner_shipping_id
        source = self.partner_id.property_stock_supplier
        destination = customer.property_stock_customer
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "partner_id": customer.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "origin": f"{self.name}, {sale_order.name}",
            "group_id": group.id,
            "company_id": self.company_id.id,
            "move_ids": [
                Command.create({
                    "name": allocation.product_id.display_name,
                    "product_id": allocation.product_id.id,
                    "product_uom_qty": allocation.product_qty,
                    "product_uom": allocation.product_uom_id.id,
                    "location_id": source.id,
                    "location_dest_id": destination.id,
                    "purchase_line_id": purchase_line.id,
                    "sale_line_id": allocation.sale_line_id.id,
                    "partner_id": customer.id,
                    "group_id": group.id,
                    "picking_type_id": picking_type.id,
                    "company_id": self.company_id.id,
                    "price_unit": purchase_line._get_stock_move_price_unit(),
                })
                for allocation in allocations
                for purchase_line in [self._get_purchase_line(allocation.product_id)]
            ],
        })
        picking.action_confirm()
        picking.action_assign()
        # Moves are created in the same order as the allocations.
        for allocation, move in zip(allocations, picking.move_ids):
            allocation.move_id = move
        return picking

    def _get_open_receipt_moves(self):
        """Return the receipt moves not yet done or cancelled."""
        return self.order_line.move_ids.filtered(
            lambda m: m.state not in ("done", "cancel")
            and m.location_dest_id.usage in ("internal", "transit")
        )

    def _get_open_receipt_quantities(self):
        """Return {product: quantity still waiting on the receipt}, in product units."""
        quantities = defaultdict(float)
        for move in self._get_open_receipt_moves():
            quantities[move.product_id] += move.product_uom._compute_quantity(
                move.product_uom_qty, move.product_id.uom_id
            )
        return quantities

    def _check_open_receipt_quantities(self, allocations):
        """Refuse to allocate quantities that are no longer in the open receipt."""
        open_quantities = self._get_open_receipt_quantities()
        for product, quantity in self._sum_by_product(allocations).items():
            if float_compare(
                quantity, open_quantities[product], precision_rounding=product.uom_id.rounding
            ) > 0:
                raise UserError(
                    _(
                        "%(product)s: %(quantity)s %(uom)s to allocate, but only %(open)s %(uom)s "
                        "are still waiting to be received on %(order)s.",
                        product=product.display_name,
                        quantity=quantity,
                        open=open_quantities[product],
                        uom=product.uom_id.name,
                        order=self.name,
                    )
                )
            
               
    def _reduce_receipt(self, allocations):
        """Remove the allocated quantities from the open receipt moves."""
        open_moves = self._get_open_receipt_moves()
        for product, quantity in self._sum_by_product(allocations).items():
            rounding = product.uom_id.rounding
            remaining = quantity
            for move in open_moves.filtered(lambda m: m.product_id == product):
                move_quantity = move.product_uom._compute_quantity(
                    move.product_uom_qty, product.uom_id
                )
                taken = min(move_quantity, remaining)
                left = move_quantity - taken
                if float_is_zero(left, precision_rounding=rounding):
                    move._action_cancel()
                else:
                    move.product_uom_qty = product.uom_id._compute_quantity(left, move.product_uom)
                remaining -= taken
                if float_is_zero(remaining, precision_rounding=rounding):
                    break

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_purchase_line(self, product):
        """Return the order line purchasing a product."""
        self.ensure_one()
        return self.order_line.filtered(lambda l: l.product_id == product)[:1]

    @api.model
    def _sum_by_product(self, allocations):
        """Return {product: total quantity} for a set of allocations."""
        quantities = defaultdict(float)
        for allocation in allocations:
            quantities[allocation.product_id] += allocation.product_qty
        return quantities

    def _get_purchased_quantities(self):
        """Return {product: purchased quantity}, in each product's own unit."""
        self.ensure_one()
        quantities = defaultdict(float)
        for line in self.order_line.filtered(lambda l: l.product_id and not l.display_type):
            quantities[line.product_id] += line.product_uom._compute_quantity(
                line.product_qty, line.product_id.uom_id
            )
        return quantities

    def _get_allocated_quantities(self):
        """Return {product: allocated quantity}, in each product's own unit."""
        self.ensure_one()
        return self._sum_by_product(self.allocation_ids)