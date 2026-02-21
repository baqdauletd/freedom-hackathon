import React, { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useDashboard } from "../state/dashboardStore";
import type { EnrichedTicket, ManagerWorkload } from "../api/types";
import "./Dashboard.css";

const COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#17becf"];

const toOption = (value: string) => value || "Все";

const sortTickets = (tickets: EnrichedTicket[], key: string, direction: "asc" | "desc") => {
  const sorted = [...tickets].sort((a, b) => {
    if (key === "priority") return a.analysis.priority - b.analysis.priority;
    if (key === "sentiment") return a.analysis.sentiment.localeCompare(b.analysis.sentiment);
    if (key === "type") return a.analysis.type.localeCompare(b.analysis.type);
    if (key === "office") return a.assignment.office.localeCompare(b.assignment.office);
    if (key === "manager") return a.assignment.managerName.localeCompare(b.assignment.managerName);
    return a.id.localeCompare(b.id);
  });
  return direction === "asc" ? sorted : sorted.reverse();
};

const useFilteredTickets = (
  tickets: EnrichedTicket[],
  search: string,
  filters: { segment: string; type: string; sentiment: string; office: string },
  sort: { key: string; direction: "asc" | "desc" },
) =>
  useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = tickets.filter((ticket) => {
      if (filters.segment !== "Все" && ticket.segment !== filters.segment) return false;
      if (filters.type !== "Все" && ticket.analysis.type !== filters.type) return false;
      if (filters.sentiment !== "Все" && ticket.analysis.sentiment !== filters.sentiment) return false;
      if (filters.office !== "Все" && ticket.assignment.office !== filters.office) return false;
      if (!term) return true;
      const haystack = [
        ticket.id,
        ticket.description,
        ticket.assignment.managerName,
        ticket.assignment.office,
        ticket.city,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });

    return sortTickets(filtered, sort.key, sort.direction);
  }, [tickets, search, filters.segment, filters.type, filters.sentiment, filters.office, sort.key, sort.direction]);

const buildPieData = (items: EnrichedTicket[], key: (ticket: EnrichedTicket) => string) => {
  const map = new Map<string, number>();
  items.forEach((ticket) => {
    const value = key(ticket);
    map.set(value, (map.get(value) ?? 0) + 1);
  });
  return Array.from(map.entries()).map(([name, value]) => ({ name, value }));
};

const buildOfficeData = (items: EnrichedTicket[]) => buildPieData(items, (ticket) => ticket.assignment.office);

const buildPriorityData = (items: EnrichedTicket[]) => {
  const buckets = [
    { name: "1-3", value: 0 },
    { name: "4-6", value: 0 },
    { name: "7-8", value: 0 },
    { name: "9-10", value: 0 },
  ];
  items.forEach((ticket) => {
    const priority = ticket.analysis.priority;
    if (priority <= 3) buckets[0].value += 1;
    else if (priority <= 6) buckets[1].value += 1;
    else if (priority <= 8) buckets[2].value += 1;
    else buckets[3].value += 1;
  });
  return buckets;
};

const buildManagerChart = (workloads: ManagerWorkload[]) =>
  workloads.map((manager) => ({
    name: manager.managerName,
    "В работе": manager.currentLoad,
    "Назначено": manager.assigned,
  }));

export const Dashboard: React.FC = () => {
  const { state, reload } = useDashboard();
  const [search, setSearch] = useState("");
  const [managerSearch, setManagerSearch] = useState("");
  const [managerOffice, setManagerOffice] = useState("Все");
  const [segment, setSegment] = useState("Все");
  const [type, setType] = useState("Все");
  const [sentiment, setSentiment] = useState("Все");
  const [office, setOffice] = useState("Все");
  const [sortKey, setSortKey] = useState("priority");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [managerSort, setManagerSort] = useState<"total" | "assigned">("total");
  const [selected, setSelected] = useState<EnrichedTicket | null>(null);

  useEffect(() => {
    reload();
  }, [reload]);

  const filteredTickets = useFilteredTickets(
    state.enrichedTickets,
    search,
    { segment, type, sentiment, office },
    { key: sortKey, direction: sortDirection },
  );

  const typeData = useMemo(() => buildPieData(state.enrichedTickets, (ticket) => ticket.analysis.type), [
    state.enrichedTickets,
  ]);
  const sentimentData = useMemo(
    () => buildPieData(state.enrichedTickets, (ticket) => ticket.analysis.sentiment),
    [state.enrichedTickets],
  );
  const officeData = useMemo(() => buildOfficeData(state.enrichedTickets), [state.enrichedTickets]);
  const priorityData = useMemo(() => buildPriorityData(state.enrichedTickets), [state.enrichedTickets]);
  const managerChart = useMemo(() => buildManagerChart(state.managerWorkloads), [state.managerWorkloads]);

  const segments = useMemo(() => ["Все", ...new Set(state.enrichedTickets.map((ticket) => ticket.segment))], [
    state.enrichedTickets,
  ]);
  const types = useMemo(() => ["Все", ...new Set(state.enrichedTickets.map((ticket) => ticket.analysis.type))], [
    state.enrichedTickets,
  ]);
  const sentiments = useMemo(
    () => ["Все", ...new Set(state.enrichedTickets.map((ticket) => ticket.analysis.sentiment))],
    [state.enrichedTickets],
  );
  const offices = useMemo(
    () => ["Все", ...new Set(state.enrichedTickets.map((ticket) => ticket.assignment.office))],
    [state.enrichedTickets],
  );

  const managerOffices = useMemo(
    () => ["Все", ...new Set(state.managerWorkloads.map((manager) => manager.office))],
    [state.managerWorkloads],
  );

  const filteredManagers = useMemo(() => {
    const term = managerSearch.trim().toLowerCase();
    const filtered = state.managerWorkloads.filter((manager) => {
      if (managerOffice !== "Все" && manager.office !== managerOffice) return false;
      if (!term) return true;
      const haystack = [manager.managerName, manager.office].join(" ").toLowerCase();
      return haystack.includes(term);
    });

    return [...filtered].sort((a, b) => {
      if (managerSort === "assigned") return b.assigned - a.assigned;
      return b.total - a.total;
    });
  }, [state.managerWorkloads, managerSearch, managerOffice, managerSort]);

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <div>
          <h1>Ночная обработка обращений</h1>
          <p>Автоматическое распределение тикетов, аналитика и нагрузка по офисам.</p>
        </div>
        <button className="btn" onClick={reload} disabled={state.loading}>
          {state.loading ? "Загрузка..." : "Обновить"}
        </button>
      </header>

      {state.error && (
        <div className="banner banner--error">
          Ошибка загрузки: {state.error}. Проверьте доступность CSV в `public`.
        </div>
      )}

      <section className="dashboard__grid">
        <div className="card">
          <h3>Типы обращений</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie dataKey="value" data={typeData} innerRadius={50} outerRadius={80}>
                {typeData.map((_, index) => (
                  <Cell key={`type-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3>Тональность</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie dataKey="value" data={sentimentData} innerRadius={50} outerRadius={80}>
                {sentimentData.map((_, index) => (
                  <Cell key={`sent-${index}`} fill={COLORS[(index + 2) % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3>Приоритетность</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={priorityData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#1f77b4" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3>Нагрузка по офисам</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={officeData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#2ca02c" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="dashboard__grid dashboard__grid--wide">
        <div className="card">
          <h3>Нагрузка менеджеров</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={managerChart}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" hide />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="В работе" stackId="a" fill="#8c564b" radius={[8, 8, 0, 0]} />
              <Bar dataKey="Назначено" stackId="a" fill="#17becf" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card">
        <div className="table__toolbar">
          <input
            className="input"
            placeholder="Поиск по описанию, офису, менеджеру"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select className="select" value={segment} onChange={(event) => setSegment(toOption(event.target.value))}>
            {segments.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select className="select" value={type} onChange={(event) => setType(toOption(event.target.value))}>
            {types.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            className="select"
            value={sentiment}
            onChange={(event) => setSentiment(toOption(event.target.value))}
          >
            {sentiments.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select className="select" value={office} onChange={(event) => setOffice(toOption(event.target.value))}>
            {offices.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select className="select" value={sortKey} onChange={(event) => setSortKey(event.target.value)}>
            <option value="priority">Сортировка: приоритет</option>
            <option value="type">Сортировка: тип</option>
            <option value="sentiment">Сортировка: тональность</option>
            <option value="office">Сортировка: офис</option>
            <option value="manager">Сортировка: менеджер</option>
          </select>
          <button
            className="btn btn--ghost"
            onClick={() => setSortDirection(sortDirection === "asc" ? "desc" : "asc")}
          >
            {sortDirection === "asc" ? "По возрастанию" : "По убыванию"}
          </button>
        </div>

        <div className="table__wrapper">
          <table className="table">
            <thead>
              <tr>
                <th>GUID</th>
                <th>Сегмент</th>
                <th>Тип</th>
                <th>Тональность</th>
                <th>Приоритет</th>
                <th>Язык</th>
                <th>Офис</th>
                <th>Менеджер</th>
                <th>Город</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filteredTickets.map((ticket) => (
                <tr key={ticket.id}>
                  <td className="mono">{ticket.id.slice(0, 8)}</td>
                  <td>{ticket.segment}</td>
                  <td>{ticket.analysis.type}</td>
                  <td>{ticket.analysis.sentiment}</td>
                  <td>{ticket.analysis.priority}</td>
                  <td>{ticket.analysis.language}</td>
                  <td>{ticket.assignment.office}</td>
                  <td>{ticket.assignment.managerName}</td>
                  <td>{ticket.city}</td>
                  <td>
                    <button className="btn btn--small" onClick={() => setSelected(ticket)}>
                      Explain
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <div className="table__toolbar">
          <input
            className="input"
            placeholder="Поиск менеджера"
            value={managerSearch}
            onChange={(event) => setManagerSearch(event.target.value)}
          />
          <select
            className="select"
            value={managerOffice}
            onChange={(event) => setManagerOffice(toOption(event.target.value))}
          >
            {managerOffices.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select className="select" value={managerSort} onChange={(event) => setManagerSort(event.target.value as "total" | "assigned")}>
            <option value="total">Сортировка: всего</option>
            <option value="assigned">Сортировка: назначено</option>
          </select>
        </div>

        <div className="table__wrapper">
          <table className="table">
            <thead>
              <tr>
                <th>Менеджер</th>
                <th>Офис</th>
                <th>В работе</th>
                <th>Назначено</th>
                <th>Всего</th>
              </tr>
            </thead>
            <tbody>
              {filteredManagers.map((manager) => (
                <tr key={manager.managerId}>
                  <td>{manager.managerName}</td>
                  <td>{manager.office}</td>
                  <td>{manager.currentLoad}</td>
                  <td>{manager.assigned}</td>
                  <td>{manager.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <div className="drawer">
          <div className="drawer__overlay" onClick={() => setSelected(null)} />
          <div className="drawer__content">
            <div className="drawer__header">
              <div>
                <h3>Explain: {selected.id.slice(0, 8)}</h3>
                <p>{selected.assignment.managerName}</p>
              </div>
              <button className="btn btn--ghost" onClick={() => setSelected(null)}>
                Закрыть
              </button>
            </div>
            <div className="drawer__body">
              <div>
                <h4>Summary</h4>
                <p>{selected.analysis.summary}</p>
              </div>
              <div>
                <h4>Recommendation</h4>
                <p>{selected.analysis.recommendation}</p>
              </div>
              <div>
                <h4>Why this manager</h4>
                <ul className="list">
                  {selected.assignment.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
