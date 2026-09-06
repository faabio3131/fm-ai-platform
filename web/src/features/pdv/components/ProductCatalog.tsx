"use client";

import { Search, ShoppingCart } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { CatalogItem } from "@/features/pdv/services/pdv-api";
import { cartActions, formatCurrency, moneyToCents } from "@/features/pdv/store/cart-store";
import { cn } from "@/lib/utils";

interface ProductCatalogProps {
  products: CatalogItem[];
  loading?: boolean;
}

const ALL_CATEGORIES = "Todos";

export function ProductCatalog({ products, loading = false }: ProductCatalogProps) {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState(ALL_CATEGORIES);

  const categories = useMemo(() => {
    const values = new Set<string>();
    for (const product of products) {
      if (product.categoria?.trim()) {
        values.add(product.categoria.trim());
      }
    }
    return [ALL_CATEGORIES, ...Array.from(values).sort((a, b) => a.localeCompare(b, "pt-BR"))];
  }, [products]);

  const filteredProducts = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("pt-BR");

    return products.filter((product) => {
      const matchesCategory =
        activeCategory === ALL_CATEGORIES || product.categoria === activeCategory;
      const matchesSearch =
        normalizedSearch.length === 0 ||
        product.nome.toLocaleLowerCase("pt-BR").includes(normalizedSearch) ||
        product.id.toLocaleLowerCase("pt-BR").includes(normalizedSearch);

      return product.disponivel && matchesCategory && matchesSearch;
    });
  }, [activeCategory, products, search]);

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="relative">
        <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoFocus
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar produto, código ou categoria"
          className="h-14 rounded-xl bg-card pl-12 pr-4 text-base shadow-sm"
          aria-label="Buscar produtos do catálogo"
        />
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {categories.map((category) => {
          const active = activeCategory === category;
          return (
            <button
              key={category}
              type="button"
              onClick={() => setActiveCategory(category)}
              className={cn(
                "min-h-12 shrink-0 rounded-xl border px-5 text-sm font-semibold transition active:scale-[0.98]",
                active
                  ? "border-primary bg-primary text-primary-foreground shadow-sm"
                  : "bg-card text-foreground hover:bg-muted",
              )}
            >
              {category}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {loading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, index) => (
              <div key={index} className="h-36 animate-pulse rounded-2xl border bg-card" />
            ))}
          </div>
        ) : filteredProducts.length === 0 ? (
          <div className="flex min-h-64 items-center justify-center rounded-2xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
            Nenhum produto disponível para este filtro.
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {filteredProducts.map((product) => (
              <button
                key={product.id}
                type="button"
                onClick={() => cartActions.addItem(product)}
                className="group flex min-h-36 flex-col justify-between rounded-2xl border bg-card p-4 text-left shadow-sm transition hover:border-primary/50 hover:shadow-md active:scale-[0.985]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {product.categoria || "Sem categoria"}
                    </p>
                    <h3 className="mt-1 text-base font-semibold leading-tight text-foreground">
                      {product.nome}
                    </h3>
                  </div>
                  <ShoppingCart className="size-5 shrink-0 text-primary opacity-60 transition group-hover:opacity-100" />
                </div>

                <div className="flex items-end justify-between gap-3">
                  <span className="truncate font-mono text-[11px] text-muted-foreground">
                    {product.id}
                  </span>
                  <Badge className="shrink-0 px-3 py-1 text-sm font-bold tabular-nums">
                    {formatCurrency(moneyToCents(product.preco))}
                  </Badge>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
