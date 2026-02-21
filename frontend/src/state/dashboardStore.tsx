import React, { createContext, useCallback, useContext, useMemo, useReducer } from "react";
import { loadBusinessUnits } from "../api/dashboards";
import { loadManagers } from "../api/managers";
import { loadTickets } from "../api/tickets";
import type {
  BusinessUnit,
  EnrichedTicket,
  Manager,
  ManagerWorkload,
  Sentiment,
  Ticket,
  TicketAnalysis,
  TicketLanguage,
  TicketType,
} from "../api/types";

const MAX_RETRIES = 2;

const typeRules: Array<{ type: TicketType; match: RegExp }> = [
  { type: "Мошеннические действия", match: /мошен/iu },
  { type: "Неработоспособность приложения", match: /не работает|ошибк|краш|сбой|приложен/iu },
  { type: "Смена данных", match: /смена|изменен|обновлен|обновить|замен/iu },
  { type: "Жалоба", match: /жалоб|недоволен|плохо/iu },
  { type: "Претензия", match: /претенз|возмещ|ущерб/iu },
  { type: "Спам", match: /спам|реклам/iu },
];

const sentimentRules: Array<{ sentiment: Sentiment; match: RegExp }> = [
  { sentiment: "Позитивный", match: /спасибо|благодар|отлично|класс/iu },
  { sentiment: "Негативный", match: /ужас|плохо|недоволен|не работает|претенз|жалоб/iu },
];

const recommendationByType: Record<TicketType, string> = {
  "Жалоба": "Зафиксировать проблему, предложить решение и контрольный срок обратной связи.",
  "Смена данных": "Проверить личность клиента и оформить изменение данных в системе.",
  "Консультация": "Дать пошаговую инструкцию и убедиться, что клиент понял действия.",
  "Претензия": "Собрать детали инцидента, подготовить ответ и согласовать сроки разбора.",
  "Неработоспособность приложения": "Проверить статус сервиса, собрать логи и направить в техподдержку.",
  "Мошеннические действия": "Эскалировать в безопасность, зафиксировать детали и приостановить операции.",
  "Спам": "Верифицировать обращение и при необходимости закрыть как нерелевантное.",
};

const kazakhChars = /[ӘәҒғҚқҢңӨөҮүҰұҺһ]/;
const englishChars = /[A-Za-z]/;

const detectLanguage = (text: string): TicketLanguage => {
  if (kazakhChars.test(text)) return "KZ";
  if (englishChars.test(text) && !/[А-Яа-яЁё]/.test(text)) return "ENG";
  if (englishChars.test(text)) {
    const englishRatio = text.replace(/[^A-Za-z]/g, "").length / Math.max(text.length, 1);
    if (englishRatio > 0.35) return "ENG";
  }
  return "RU";
};

const classifyType = (text: string): TicketType => {
  const found = typeRules.find((rule) => rule.match.test(text));
  return found?.type ?? "Консультация";
};

const classifySentiment = (text: string): Sentiment => {
  const found = sentimentRules.find((rule) => rule.match.test(text));
  return found?.sentiment ?? "Нейтральный";
};

const computePriority = (segment: Ticket["segment"], type: TicketType, sentiment: Sentiment, text: string) => {
  let base = segment === "VIP" ? 8 : segment === "Priority" ? 7 : 5;
  if (type === "Мошеннические действия" || type === "Неработоспособность приложения") base += 2;
  if (sentiment === "Негативный") base += 1;
  if (/срочно|немедлен/iu.test(text)) base += 2;
  return Math.min(10, Math.max(1, base));
};

const summarize = (text: string) => {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return "Клиент не указал деталей.";
  return clean.length > 160 ? `${clean.slice(0, 160)}...` : clean;
};

const analyzeTicket = (ticket: Ticket): TicketAnalysis => {
  const language = detectLanguage(ticket.description);
  const type = classifyType(ticket.description);
  const sentiment = classifySentiment(ticket.description);
  const priority = computePriority(ticket.segment, type, sentiment, ticket.description);
  const summary = summarize(ticket.description);
  return {
    type,
    sentiment,
    priority,
    language,
    summary,
    recommendation: recommendationByType[type],
  };
};

const normalize = (value: string) => value.toLowerCase();

const pickOffice = (ticket: Ticket, offices: BusinessUnit[]) => {
  const country = normalize(ticket.country || "");
  const city = normalize(ticket.city || "");
  const region = normalize(ticket.region || "");

  const knownOffices = offices.map((office) => office.office);
  const normalizedOffices = knownOffices.map((office) => normalize(office));

  const directMatchIndex = normalizedOffices.findIndex((office) => city.includes(office) || region.includes(office));
  if (directMatchIndex >= 0) return knownOffices[directMatchIndex];

  if (!country || !country.includes("казахстан")) {
    return undefined;
  }

  return undefined;
};

const deterministicSplit = (ticketId: string, a: string, b: string) => {
  const hash = ticketId.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return hash % 2 === 0 ? a : b;
};

const selectOffice = (ticket: Ticket, offices: BusinessUnit[]) => {
  const office = pickOffice(ticket, offices);
  if (office) return office;
  return deterministicSplit(ticket.id, "Астана", "Алматы");
};

const managerMatches = (manager: Manager, ticket: Ticket, analysis: TicketAnalysis) => {
  if ((ticket.segment === "VIP" || ticket.segment === "Priority") && !manager.skills.includes("VIP")) return false;
  if (analysis.type === "Смена данных" && !manager.role.toLowerCase().includes("глав")) return false;
  if (analysis.language === "KZ" && !manager.skills.includes("KZ")) return false;
  if (analysis.language === "ENG" && !manager.skills.includes("ENG")) return false;
  return true;
};

const buildAssignments = (tickets: Ticket[], managers: Manager[], offices: BusinessUnit[]) => {
  const assignments: EnrichedTicket[] = [];
  const assignedCount: Record<string, number> = {};
  const rrCounter: Record<string, number> = {};

  tickets.forEach((ticket) => {
    const analysis = analyzeTicket(ticket);
    const office = selectOffice(ticket, offices);

    const candidates = managers
      .filter((manager) => manager.office === office)
      .filter((manager) => managerMatches(manager, ticket, analysis));

    const fallback = managers.filter((manager) => managerMatches(manager, ticket, analysis));
    const pool = candidates.length > 0 ? candidates : fallback;

    const ranked = [...pool].sort((a, b) => {
      const loadA = a.currentLoad + (assignedCount[a.id] ?? 0);
      const loadB = b.currentLoad + (assignedCount[b.id] ?? 0);
      return loadA - loadB;
    });

    const topTwo = ranked.slice(0, 2);
    const chosenIndex = topTwo.length > 1 ? (rrCounter[office] ?? 0) % 2 : 0;
    const chosen = topTwo[chosenIndex] ?? ranked[0] ?? managers[0];

    if (chosen) {
      assignedCount[chosen.id] = (assignedCount[chosen.id] ?? 0) + 1;
    }

    rrCounter[office] = (rrCounter[office] ?? 0) + 1;

    const reasons = [
      `Офис: ${office}`,
      `Язык: ${analysis.language}`,
      `Тип: ${analysis.type}`,
      `Сегмент: ${ticket.segment}`,
      `Доступен по навыкам: ${chosen?.skills.join(", ") || "нет"}`,
      "Балансировка: минимальная нагрузка + round robin",
    ];

    assignments.push({
      ...ticket,
      analysis,
      assignment: {
        ticketId: ticket.id,
        office,
        managerId: chosen?.id ?? "",
        managerName: chosen?.name ?? "Не назначен",
        reasons,
      },
    });
  });

  return assignments;
};

const buildManagerWorkloads = (managers: Manager[], tickets: EnrichedTicket[]): ManagerWorkload[] => {
  const counts: Record<string, number> = {};
  tickets.forEach((ticket) => {
    const managerId = ticket.assignment.managerId;
    if (!managerId) return;
    counts[managerId] = (counts[managerId] ?? 0) + 1;
  });

  return managers.map((manager) => {
    const assigned = counts[manager.id] ?? 0;
    return {
      managerId: manager.id,
      managerName: manager.name,
      office: manager.office,
      currentLoad: manager.currentLoad,
      assigned,
      total: manager.currentLoad + assigned,
    };
  });
};

export type DashboardState = {
  loading: boolean;
  error: string | null;
  tickets: Ticket[];
  managers: Manager[];
  offices: BusinessUnit[];
  enrichedTickets: EnrichedTicket[];
  managerWorkloads: ManagerWorkload[];
};

type DashboardAction =
  | { type: "LOAD_START" }
  | { type: "LOAD_SUCCESS"; payload: Omit<DashboardState, "loading" | "error"> }
  | { type: "LOAD_ERROR"; payload: string };

const initialState: DashboardState = {
  loading: false,
  error: null,
  tickets: [],
  managers: [],
  offices: [],
  enrichedTickets: [],
  managerWorkloads: [],
};

const dashboardReducer = (state: DashboardState, action: DashboardAction): DashboardState => {
  switch (action.type) {
    case "LOAD_START":
      return { ...state, loading: true, error: null };
    case "LOAD_SUCCESS":
      return { loading: false, error: null, ...action.payload };
    case "LOAD_ERROR":
      return { ...state, loading: false, error: action.payload };
    default:
      return state;
  }
};

const DashboardContext = createContext<{
  state: DashboardState;
  reload: () => Promise<void>;
} | null>(null);

const loadAllData = async () => {
  const [tickets, managers, offices] = await Promise.all([loadTickets(), loadManagers(), loadBusinessUnits()]);
  const enrichedTickets = buildAssignments(tickets, managers, offices);
  const managerWorkloads = buildManagerWorkloads(managers, enrichedTickets);

  return {
    tickets,
    managers,
    offices,
    enrichedTickets,
    managerWorkloads,
  };
};

export const DashboardProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(dashboardReducer, initialState);

  const reload = useCallback(async () => {
    dispatch({ type: "LOAD_START" });

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
      try {
        const payload = await loadAllData();
        dispatch({ type: "LOAD_SUCCESS", payload });
        return;
      } catch (error) {
        if (attempt >= MAX_RETRIES) {
          dispatch({ type: "LOAD_ERROR", payload: error instanceof Error ? error.message : "Ошибка загрузки" });
          return;
        }
      }
    }
  }, []);

  const value = useMemo(() => ({ state, reload }), [state, reload]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
};

export const useDashboard = () => {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("DashboardProvider is missing");
  return ctx;
};
