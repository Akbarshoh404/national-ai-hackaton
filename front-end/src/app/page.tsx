"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { homeFor, useAccount } from "@/lib/auth";

export default function Home() {
  const account = useAccount();
  const router = useRouter();
  useEffect(() => {
    if (account === null) router.replace("/login");
    else if (account) router.replace(homeFor(account));
  }, [account, router]);
  return null;
}
