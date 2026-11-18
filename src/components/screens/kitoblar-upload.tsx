"use client";

import { Upload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { useUploadCommit, useUploadPreview } from "@/lib/api/hooks";
import type { UploadPreview } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";

const SAMPLE_ROWS = [
  ["Sana", "Mahsulot nomi", "Kontragent", "Summa"],
  ["12.11.2026", "iPhone 13 128GB", "TechOpt Wholesale", "31 000 000"],
  ["08.11.2026", "Samsung A55", "MobiGross", "13 360 000"],
  ["05.11.2026", "Reklama", "Meta", "4 200 000"],
];

function parseDelimited(text: string) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  const first = lines[0] ?? "";
  const delimiter = [";", "\t", ","].sort((a, b) => first.split(b).length - first.split(a).length)[0];
  return lines.map((line) => line.split(delimiter).map((cell) => cell.trim().replace(/^"|"$/g, "")));
}

export function UploadPanel({ onClose }: { onClose: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const photoRef = useRef<HTMLInputElement>(null);
  const preview = useUploadPreview();
  const commit = useUploadCommit();
  const [over, setOver] = useState(false);
  const [data, setData] = useState<UploadPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [sampled, setSampled] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const read = async (file: File) => {
    setDone(null);
    const isText = /\.(csv|tsv|txt)$/i.test(file.name);
    const rows = isText ? parseDelimited(await file.text()) : SAMPLE_ROWS;
    setSampled(!isText);
    preview.mutate(
      { filename: file.name, rows },
      {
        onSuccess: (result) => {
          setData(result);
          setMapping(Object.fromEntries(result.columns.map((c) => [c.source, c.target])));
        },
      },
    );
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void read(file);
  };

  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="serif text-[28px]">Fayldan yuklash</h2>
          <p className="mt-1 text-[14px] text-text-2">Excel, CSV yoki 1C eksporti. Import qilishdan oldin ustunlarni tekshirasiz.</p>
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
            <p className="text-[13px] text-text-2">.xlsx, .csv, .xml (1C)</p>
            <Button onClick={() => fileRef.current?.click()} disabled={preview.isPending}>
              Faylni tanlash
            </Button>
            <input
              ref={fileRef}
              type="file"
              aria-label="Faylni tanlash"
              accept=".csv,.tsv,.txt,.xlsx,.xls,.xml"
              className="sr-only"
              tabIndex={-1}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void read(file);
                e.target.value = "";
              }}
            />
          </div>
          <div className="panel mt-3 flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <p className="text-[14px] font-medium">Faktura rasmi</p>
              <p className="text-[13px] text-text-2">Qog‘oz fakturani suratga olib yuklang.</p>
            </div>
            <Button onClick={() => photoRef.current?.click()}>Rasm yuklash</Button>
            <input
              ref={photoRef}
              type="file"
              aria-label="Faktura rasmini yuklash"
              accept="image/*"
              className="sr-only"
              tabIndex={-1}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) commit.mutate({ filename: file.name, rows: 1, mapping: {} }, { onSuccess: () => setDone(`${file.name} qabul qilindi va kitoblarga qo‘shildi.`) });
                e.target.value = "";
              }}
            />
          </div>
        </>
      ) : (
        <div className="mt-4">
          <p className="text-[14px]">
            <span className="mono font-medium">{data.filename}</span> <span className="text-text-2">· {data.rows} ta yozuv</span>
          </p>
          {sampled ? <p className="mt-1 text-[13px] text-warning">Demo rejimida bu format o‘qilmaydi, ustunlar namuna sifatida ko‘rsatilgan.</p> : null}
          <div className="panel mt-3 overflow-x-auto p-4">
            <table className="data-table">
              <thead>
                <tr>
                  {data.columns.map((c) => (
                    <th key={c.source} className="min-w-[140px] align-top">
                      <label htmlFor={`map-${c.source}`} className="mb-1 block">
                        {c.source}
                      </label>
                      <select id={`map-${c.source}`} className="input h-11 font-normal" value={mapping[c.source] ?? "skip"} onChange={(e) => setMapping((m) => ({ ...m, [c.source]: e.target.value }))}>
                        {data.targets.map((t) => (
                          <option key={t.value} value={t.value}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.sample.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, k) => (
                      <td key={k} className="mono">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              size="lg"
              disabled={commit.isPending}
              onClick={() =>
                commit.mutate(
                  { filename: data.filename, rows: data.rows, mapping },
                  {
                    onSuccess: () => {
                      setDone(`${data.rows} ta yozuv import qilindi.`);
                      setData(null);
                    },
                  },
                )
              }
            >
              {data.rows} ta yozuvni import qilish
            </Button>
            <Button variant="plain" onClick={() => setData(null)}>
              Boshqa fayl
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
