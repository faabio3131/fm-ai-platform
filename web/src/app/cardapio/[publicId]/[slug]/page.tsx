import { CardapioPublicoWorkspace } from "@/features/cardapio-publico/components/CardapioPublicoWorkspace";

export default async function CardapioPublicoPage({
  params,
}: {
  params: Promise<{ publicId: string; slug: string }>;
}) {
  const { publicId, slug } = await params;
  return <CardapioPublicoWorkspace publicId={publicId} slug={slug} />;
}
