"use client";

import { Upload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { FIELD_LABELS, type UploadPreviewData } from "@/lib/api/backend/books";
import { ApiError } from "@/lib/api/client";
import { downloadUploadTemplate, useInvoiceUpload, useUploadCommit, useUploadPreview } from "@/lib/api/hooks";
import { dateShort, soum } from "@/lib/format";
import { cn } from "@/lib/utils";

const SKIP = "skip";
const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Fayl o‘qilmadi. Qayta urinib ko‘ring.");

export function UploadPanel({ onClose }: { onClose: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const photoRef = useRef<HTMLInputElement>(null);
  const preview = useUploadPreview();
  const commit = useUploadCommit();
  const invoice = useInvoiceUpload();
  const [over, setOver] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [data, setData] = useState<UploadPreviewData | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [done, setDone] = useState<string | null>(null);

  const runPreview = (f: File, m?: Record<string, string | null>) =>
    preview.mutate(
      { file: f, mapping: m },
      {
        onSuccess: (result) => {
          setData(result);
          setMapping(m ?? Object.fromEntries(result.columns.map((c) => [c, result.mapping[c]?.field ?? null])));
        },
      },
    );

  const read = (f: File) => {
    setDone(null);
    setFile(f);
    runPreview(f);
  };

  const remap = (column: string, value: string) => {
    const next = { ...mapping, [column]: value === SKIP ? null : value };
    setMapping(next);
    if (file) runPreview(file, next);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files[0];
    if (f) read(f);
  };

  const options = data ? [{ value: SKIP, label: "O‘tkazib yuborish" }, ...data.fields.map((f) => ({ value: f, label: FIELD_LABELS[f] ?? f }))] : [];

  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="serif text-[28px]">Fayldan yuklash</h2>
          <p className="mt-1 text-[14px] text-text-2">Excel yoki CSV eksporti. Import qilishdan oldin ustunlarni tekshirasiz.</p>
        </div>
        <Button variant="plain" onClick={onClose}>
          Tekshiruvga qaytish
        </Button>
      </div>

      {done ? (
        <p role="status" className="panel mt-4 p-4 text-[14px]">
          {done}
        </p>
      ) : null}

      {!data ? (
        <>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={onDrop}
            className={cn("mt-4 flex flex-col items-start gap-2 rounded-[16px] border border-dashed border-border-strong p-5 transition-colors duration-150", over && "border-accent bg-accent-soft")}
          >
            <Upload size={20} strokeWidth={1.75} aria-hidden />
            <p className="text-[14px] font-medium">Faylni shu yerga tashlang</p>
            <p className="text-[13px] text-text-2">.xlsx, .xls, .csv · 10 MB gacha</p>
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => fileRef.current?.click()} disabled={preview.isPending}>
                {preview.isPending ? "O‘qilmoqda" : "Faylni tanlash"}
              </Button>
              <Button variant="plain" onClick={() => void downloadUploadTemplate()}>
                Namuna fayl (CSV)
              </Button>
            </div>
            {preview.isError ? (
              <p role="alert" className="text-[13px] text-danger">
                {errorText(preview.error)}
              </p>
            ) : null}
            <input
              ref={fileRef}
              type="file"
              aria-label="Faylni tanlash"
              accept=".csv,.tsv,.txt,.xlsx,.xls"
              className="sr-only"
              tabIndex={-1}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) read(f);
                e.target.value = "";
              }}
            />
          </div>
          <div className="panel mt-3 flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <p className="text-[14px] font-medium">Faktura rasmi</p>
              <p className="text-[13px] text-text-2">Qog‘oz fakturani suratga olib yuklang.</p>
              {invoice.isError ? (
                <p role="alert" className="mt-1 text-[13px] text-danger">
                  {errorText(invoice.error)}
                </p>
              ) : null}
            </div>
            <Button disabled={invoice.isPending} onClick={() => photoRef.current?.click()}>
              {invoice.isPending ? "O‘qilmoqda" : "Rasm yuklash"}
            </Button>
            <input
              ref={photoRef}
              type="file"
              aria-label="Faktura rasmini yuklash"
              accept="image/*"
              className="sr-only"
              tabIndex={-1}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f)
                  invoice.mutate(f, {
                    onSuccess: (r) => setDone(r.created_ids.length ? `${f.name}: ${r.created_ids.length} ta yozuv kitoblarga qo‘shildi.` : `${f.name}: rasmdan yozuv topilmadi.`),
                  });
                e.target.value = "";
              }}
            />
          </div>
        </>
      ) : (
        <div className="mt-4">
          <p className="text-[14px]">
            <span className="mono font-medium">{file?.name}</span> <span className="text-text-2">· {data.total_rows} ta qator</span>
          </p>
          <div className="panel mt-3 overflow-x-auto p-4">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Fayldagi ustun</th>
                  <th className="min-w-[180px]">Maydon</th>
                  <th className="r">Ishonch</th>
                </tr>
              </thead>
              <tbody>
                {data.columns.map((c) => (
                  <tr key={c}>
                    <td className="mono">
                      <label htmlFor={`map-${c}`}>{c}</label>
                    </td>
                    <td>
                      <Select id={`map-${c}`} className="font-normal" value={mapping[c] ?? SKIP} onValueChange={(value) => remap(c, value)} options={options} />
                    </td>
                    <td className="r mono text-text-2">{data.mapping[c]?.field ? `${Math.round(data.mapping[c].confidence * 100)}%` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.rows.length ? (
            <div className="panel mt-3 overflow-x-auto p-4">
              <p className="mb-2 text-[13px] text-text-2">Birinchi {data.rows.length} ta qator, import qilinganda shunday yoziladi</p>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Sana</th>
                    <th>Turi</th>
                    <th>Toifa</th>
                    <th>Kontragent</th>
                    <th className="r">Jami</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i}>
                      <td className="mono">{dateShort(r.date)}</td>
                      <td>{r.type === "income" ? "Kirim" : "Chiqim"}</td>
                      <td>{[r.category, r.model].filter(Boolean).join(" · ")}</td>
                      <td className="text-text-2">{r.counterparty ?? "—"}</td>
                      <td className="r mono">{soum(r.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {data.errors.length ? (
            <ul role="alert" className="mt-3 flex flex-col gap-1 text-[13px] text-danger">
              {data.errors.slice(0, 5).map((e) => (
                <li key={`${e.row}-${e.error}`}>{e.row ? `${e.row}-qator: ${e.error}` : e.error}</li>
              ))}
            </ul>
          ) : null}
          {commit.isError ? (
            <p role="alert" className="mt-3 text-[13px] text-danger">
              {errorText(commit.error)}
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              size="lg"
              disabled={commit.isPending || preview.isPending || !data.rows.length || !file}
              onClick={() =>
                file &&
                commit.mutate(
                  { file, mapping },
                  {
                    onSuccess: (r) => {
                      setDone(`${r.created} ta yozuv import qilindi${r.errors.length ? `, ${r.errors.length} ta qator xato` : ""}.`);
                      setData(null);
                      setFile(null);
                    },
                  },
                )
              }
            >
              {data.total_rows} ta qatorni import qilish
            </Button>
            <Button
              variant="plain"
              onClick={() => {
                setData(null);
                setFile(null);
              }}
            >
              Boshqa fayl
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
