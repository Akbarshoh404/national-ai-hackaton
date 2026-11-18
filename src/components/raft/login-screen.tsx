"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { resetDemo } from "@/lib/api/fixtures/server";
import { ACCOUNTS, homeFor, setAccount, type Account } from "@/lib/auth";

export function LoginScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const [resetDone, setResetDone] = useState(false);

  const choose = (account: Account) => {
    setAccount(account.id);
    qc.clear();
    router.push(homeFor(account));
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[640px] flex-col justify-center gap-5 p-5">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-[12px] bg-text text-[16px] font-semibold text-white">R</span>
        <span className="text-[17px] font-semibold">Raft</span>
      </div>
      <section className="tile">
        <h1 className="serif text-[32px]">Demo hisobini tanlang</h1>
        <p className="mt-1 text-text-2">Har bir hisob o‘z ekranlari va huquqlari bilan ochiladi.</p>
        <ul className="mt-4">
          {ACCOUNTS.map((account) => (
            <li key={account.id} className="border-t border-[rgb(15_23_22/0.06)] first:border-t-0">
              <button
                type="button"
                onClick={() => choose(account)}
                className="grid min-h-[64px] w-full grid-cols-[minmax(0,1fr)_auto] gap-x-4 rounded-[16px] px-3 py-3 text-left transition-colors duration-150 hover:bg-[var(--nested)]"
              >
                <span className="text-[14px] font-semibold">{account.name}</span>
                <span className="t-cap self-center text-right">{account.role}</span>
                <span className="col-span-2 mt-0.5 text-[13px] text-text-2">{account.about}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
      <div className="flex items-center gap-2 text-[13px] text-text-2">
        <button
          type="button"
          className="btn btn-plain -ml-2"
          onClick={() => {
            resetDemo();
            qc.clear();
            setResetDone(true);
          }}
        >
          Demo ma’lumotlarini tiklash
        </button>
        {resetDone ? <span role="status">Boshlang‘ich holatga qaytarildi.</span> : null}
      </div>
    </main>
  );
}
