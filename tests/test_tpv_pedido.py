# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError


@tagged('tpv_pedidos')
class TestTpvPedido(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.TpvPedido = cls.env['tpv.pedido']
        cls.TpvNotaCategoria = cls.env['tpv.nota.categoria']
        cls.ProductProduct = cls.env['product.product']
        cls.PosConfig = cls.env['pos.config']
        cls.ResPartner = cls.env['res.partner']

        # Crear producto de prueba
        cls.product_magdalenas = cls.ProductProduct.create({
            'name': 'Magdalenas Cuadradas',
            'lst_price': 2.50,
            'type': 'consu',
        })
        cls.product_croissants = cls.ProductProduct.create({
            'name': 'Croissants',
            'lst_price': 1.80,
            'type': 'consu',
        })

        # Crear POS config de prueba
        cls.pos_config = cls.PosConfig.create({
            'name': 'Tienda Centro',
        })

        # Crear categoría de nota de prueba
        cls.nota_urgente = cls.TpvNotaCategoria.create({
            'name': 'Urgente',
            'sequence': 10,
            'activa': True,
        })

    def test_create_pedido_encargo(self):
        """Test: crear un pedido tipo ENCARGO"""
        pedido = self.TpvPedido.create({
            'pos_config_id': self.pos_config.id,
            'tipo_pedido': 'encargo',
            'nota_general': 'Entrega antes de las 10',
            'line_ids': [(0, 0, {
                'product_id': self.product_magdalenas.id,
                'qty': 50,
                'nota_linea': 'Para el martes',
                'nota_categoria_id': self.nota_urgente.id,
            })],
        })
        self.assertEqual(pedido.tipo_pedido, 'encargo')
        self.assertTrue(pedido.es_encargo)
        self.assertEqual(len(pedido.line_ids), 1)
        self.assertEqual(pedido.line_ids[0].product_id, self.product_magdalenas)
        self.assertEqual(pedido.line_ids[0].qty, 50)
        self.assertEqual(pedido.state, 'draft')

    def test_create_pedido_tienda(self):
        """Test: crear un pedido tipo PEDIDO TIENDA"""
        pedido = self.TpvPedido.create({
            'pos_config_id': self.pos_config.id,
            'tipo_pedido': 'pedido_tienda',
            'line_ids': [
                (0, 0, {
                    'product_id': self.product_magdalenas.id,
                    'qty': 100,
                }),
                (0, 0, {
                    'product_id': self.product_croissants.id,
                    'qty': 30,
                }),
            ],
        })
        self.assertEqual(pedido.tipo_pedido, 'pedido_tienda')
        self.assertFalse(pedido.es_encargo)
        self.assertEqual(len(pedido.line_ids), 2)

    def test_confirm_pedido_creates_sale_order(self):
        """Test: confirmar pedido crea sale.order confirmado"""
        pedido = self.TpvPedido.create({
            'pos_config_id': self.pos_config.id,
            'tipo_pedido': 'pedido_tienda',
            'line_ids': [(0, 0, {
                'product_id': self.product_magdalenas.id,
                'qty': 20,
            })],
        })
        pedido.action_confirm()
        self.assertEqual(pedido.state, 'confirmed')
        self.assertTrue(pedido.sale_order_id)
        self.assertEqual(pedido.sale_order_id.state, 'sale')
        self.assertEqual(pedido.sale_order_id.tipo_pedido_tag, 'pedido_tienda')

    def test_confirm_pedido_without_lines_raises(self):
        """Test: no se puede confirmar un pedido sin líneas"""
        pedido = self.TpvPedido.create({
            'pos_config_id': self.pos_config.id,
            'tipo_pedido': 'pedido_tienda',
        })
        with self.assertRaises(ValidationError):
            pedido.action_confirm()

    def test_sequence_generation(self):
        """Test: el nombre se genera automáticamente con la secuencia"""
        pedido = self.TpvPedido.create({
            'pos_config_id': self.pos_config.id,
            'tipo_pedido': 'pedido_tienda',
            'line_ids': [(0, 0, {
                'product_id': self.product_magdalenas.id,
                'qty': 10,
            })],
        })
        self.assertTrue(pedido.name.startswith('PED/'))

    def test_nota_categoria_active(self):
        """Test: las categorías de nota se filtran por activa"""
        cat_inactiva = self.TpvNotaCategoria.create({
            'name': 'Inactiva',
            'activa': False,
        })
        cats_activas = self.TpvNotaCategoria.search([
            ('activa', '=', True),
        ])
        self.assertIn(self.nota_urgente, cats_activas)
        self.assertNotIn(cat_inactiva, cats_activas)

    def test_line_precio_unitario_compute(self):
        """Test: el precio unitario se calcula del producto"""
        pedido = self.TpvPedido.create({
            'pos_config_id': self.pos_config.id,
            'tipo_pedido': 'pedido_tienda',
            'line_ids': [(0, 0, {
                'product_id': self.product_magdalenas.id,
                'qty': 5,
            })],
        })
        self.assertEqual(
            pedido.line_ids[0].precio_unitario,
            self.product_magdalenas.lst_price,
        )

    def test_create_pedido_from_pos(self):
        """Test: crear pedido vía método del frontend"""
        result = self.TpvPedido.create_pedido_from_pos(
            pos_config_id=self.pos_config.id,
            tipo_pedido='encargo',
            lines=[{
                'product_id': self.product_magdalenas.id,
                'qty': 15,
                'nota_linea': 'Nota de prueba',
                'nota_categoria_id': self.nota_urgente.id,
            }],
            nota_general='Entrega urgente',
        )
        self.assertTrue(result['pedido_id'])
        self.assertTrue(result['name'])
        pedido = self.TpvPedido.browse(result['pedido_id'])
        self.assertEqual(pedido.tipo_pedido, 'encargo')
        self.assertEqual(pedido.state, 'confirmed')
        self.assertEqual(len(pedido.line_ids), 1)
        self.assertEqual(pedido.line_ids[0].nota_categoria_id, self.nota_urgente)
        self.assertTrue(pedido.sale_order_id)