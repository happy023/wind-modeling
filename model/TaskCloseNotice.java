/**
 * Copyright (c) Honor Device Co.,Ltd. 2024-2025. All rights reserved.
 */
package com.hihonor.wftask.model;

import com.ptc.windchill.annotations.metadata.*;
import wt.fc.WTObject;
import wt.util.WTException;

import java.io.Externalizable;

@GenAsPersistable(superClass = WTObject.class, interfaces = Externalizable.class, properties = {
        @GeneratedProperty(name = "closeTaskId",
                type = Long.class,
                javaDoc = "workItem的Id",
                constraints = @PropertyConstraints(required = true),
                columnProperties = @ColumnProperties(index = true)),
        @GeneratedProperty(name = "userId",
                type = Long.class,
                javaDoc = "用户的userId",
                constraints = @PropertyConstraints(required = true),
                columnProperties = @ColumnProperties(index = true)),
        @GeneratedProperty(name = "userName",
                type = String.class,
                javaDoc = "用户的userName",
                columnProperties = @ColumnProperties(index = true),
                constraints = @PropertyConstraints(upperLimit = 100, required = true)),
        @GeneratedProperty(name = "str_1",
                type = String.class,
                javaDoc = "预留字段1",
                constraints = @PropertyConstraints(upperLimit = 4000)),
        @GeneratedProperty(name = "str_2",
                type = String.class,
                javaDoc = "预留字段2",
                constraints = @PropertyConstraints(upperLimit = 4000)),
        @GeneratedProperty(name = "str_3",
                type = String.class,
                javaDoc = "预留字段3",
                constraints = @PropertyConstraints(upperLimit = 4000)),
        @GeneratedProperty(name = "str_4",
                type = String.class,
                javaDoc = "预留字段4",
                constraints = @PropertyConstraints(upperLimit = 4000)),
        @GeneratedProperty(name = "str_5",
                type = String.class,
                javaDoc = "预留字段5",
                constraints = @PropertyConstraints(upperLimit = 4000)),
})
public class TaskCloseNotice extends _TaskCloseNotice {
    static final long serialVersionUID = 1;

    public static TaskCloseNotice newTaskCloseNotice() throws WTException {
        final TaskCloseNotice instance = new TaskCloseNotice();
        instance.initialize();
        return instance;
    }
}