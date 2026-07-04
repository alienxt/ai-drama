package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.dramas.Drama;

import java.time.LocalDate;

public class HongguoDtos {
    private HongguoDtos() {
    }

    public record CalendarSyncRequest(LocalDate date, Integer page) {
    }

    public record CalendarSyncResponse(LocalDate date, int page, int fetched, int filtered, int created, int updated) {
        static CalendarSyncResponse from(HongguoDramaService.CalendarSyncResult result) {
            return new CalendarSyncResponse(
                    result.date(),
                    result.page(),
                    result.fetched(),
                    result.filtered(),
                    result.created(),
                    result.updated()
            );
        }
    }

    public record ImportCandidateResponse(Drama drama) {
    }
}
