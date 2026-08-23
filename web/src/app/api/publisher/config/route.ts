import { NextResponse } from "next/server";
import {
  hasPublisherWriteAccess,
  readPublisherDocument,
  writePublisherDocument,
} from "@/lib/server-publisher-config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const { config } = await readPublisherDocument();
    return NextResponse.json({ ok: true, config });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }, { status: 404 });
  }
}

export async function PUT(request: Request) {
  if (!hasPublisherWriteAccess(request)) {
    return NextResponse.json({ ok: false, error: "Clé administrateur requise." }, { status: 401 });
  }
  try {
    const body = await request.json();
    const config = await writePublisherDocument(body);
    return NextResponse.json({ ok: true, config });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }, { status: 400 });
  }
}
