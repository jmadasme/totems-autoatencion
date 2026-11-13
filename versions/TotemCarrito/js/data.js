/**
 * data.js — Catálogo de productos alimenticios
 *
 * Define la constante inmutable PRODUCTOS con los 12 productos del catálogo.
 * Es la única fuente de verdad para los datos de productos.
 * No se modifica en tiempo de ejecución.
 *
 * @global {Array<Object>} PRODUCTOS — Lista inmutable de productos.
 */

const PRODUCTOS = Object.freeze([
  {
    id: 1,
    nombre: 'Pan Artesanal',
    descripcion: 'Pan de masa madre, horneado a leña. Crujiente por fuera, suave por dentro.',
    precio: 1500,
    imagen: 'https://picsum.photos/seed/pan/400/300',
    categoria: 'Panadería'
  },
  {
    id: 2,
    nombre: 'Lechuga Hidropónica',
    descripcion: 'Lechuga fresca cultivada en sistema hidropónico. Libre de pesticidas.',
    precio: 1200,
    imagen: 'https://picsum.photos/seed/lechuga/400/300',
    categoria: 'Verduras'
  },
  {
    id: 3,
    nombre: 'Tomate Orgánico (kg)',
    descripcion: 'Tomates orgánicos de temporada, cultivados sin químicos. Dulces y jugosos.',
    precio: 2800,
    imagen: 'https://picsum.photos/seed/tomate/400/300',
    categoria: 'Verduras'
  },
  {
    id: 4,
    nombre: 'Queso Fresco',
    descripcion: 'Queso fresco artesanal, elaborado con leche de vaca. Suave y cremoso.',
    precio: 3500,
    imagen: 'https://picsum.photos/seed/queso/400/300',
    categoria: 'Lácteos'
  },
  {
    id: 5,
    nombre: 'Huevos de Campo (12u)',
    descripcion: 'Docena de huevos de gallinas criadas en libertad. Yema de color intenso.',
    precio: 3200,
    imagen: 'https://picsum.photos/seed/huevos/400/300',
    categoria: 'Lácteos'
  },
  {
    id: 6,
    nombre: 'Miel de Abeja (500g)',
    descripcion: 'Miel pura de abeja, sin procesar. Endulzante natural lleno de propiedades.',
    precio: 4500,
    imagen: 'https://picsum.photos/seed/miel/400/300',
    categoria: 'Almacén'
  },
  {
    id: 7,
    nombre: 'Aceite de Oliva (500ml)',
    descripcion: 'Aceite de oliva extra virgen, primera presión en frío. Aroma y sabor únicos.',
    precio: 5900,
    imagen: 'https://picsum.photos/seed/aceite/400/300',
    categoria: 'Almacén'
  },
  {
    id: 8,
    nombre: 'Mermelada de Frutilla',
    descripcion: 'Mermelada artesanal de frutilla, con trozos de fruta. Sin colorantes.',
    precio: 2100,
    imagen: 'https://picsum.photos/seed/mermelada/400/300',
    categoria: 'Almacén'
  },
  {
    id: 9,
    nombre: 'Leche Entera (1L)',
    descripcion: 'Leche entera fresca, pasteurizada. De vacas alimentadas con pasto natural.',
    precio: 1100,
    imagen: 'https://picsum.photos/seed/leche/400/300',
    categoria: 'Lácteos'
  },
  {
    id: 10,
    nombre: 'Mantequilla (250g)',
    descripcion: 'Mantequilla de crema fresca, ligeramente salada. Ideal para cocina y repostería.',
    precio: 2400,
    imagen: 'https://picsum.photos/seed/mantequilla/400/300',
    categoria: 'Lácteos'
  },
  {
    id: 11,
    nombre: 'Galletas de Avena',
    descripcion: 'Galletas crujientes de avena con pasas. Horneadas artesanalmente.',
    precio: 1800,
    imagen: 'https://picsum.photos/seed/galletas/400/300',
    categoria: 'Panadería'
  },
  {
    id: 12,
    nombre: 'Café de Grano (250g)',
    descripcion: 'Café de especialidad, tostado medio. Notas de chocolate y frutos secos.',
    precio: 3900,
    imagen: 'https://picsum.photos/seed/cafe/400/300',
    categoria: 'Almacén'
  }
]);
