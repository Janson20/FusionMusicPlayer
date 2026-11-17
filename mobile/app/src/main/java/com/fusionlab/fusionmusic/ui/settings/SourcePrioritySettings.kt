package com.fusionlab.fusionmusic.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.SourceRegistryMeta

@Composable
fun SourcePrioritySettings(container: AppContainer, revision: Long) {
    val config = container.config
    val known = SourceRegistryMeta.SOURCE_META.map { it.id }
    var order by remember(revision) {
        val saved = config.getStringList("sources.priority").filter { known.contains(it) }
        mutableStateOf((saved + known.filterNot { saved.contains(it) }).distinct())
    }
    val names = SourceRegistryMeta.SOURCE_META.associate { it.id to it.name }
    Column {
        Text(
            "越靠前越优先参与搜索排序与跨源兜底。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 16.dp)
        )
        for ((index, id) in order.withIndex()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    (index + 1).toString() + ". " + (names[id] ?: id),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f)
                )
                TextButton(
                    enabled = index > 0,
                    onClick = {
                        val next = order.toMutableList()
                        val item = next.removeAt(index)
                        next.add(index - 1, item)
                        order = next
                        config.setStringList("sources.priority", next)
                    }
                ) { Text("上移") }
                TextButton(
                    enabled = index < order.lastIndex,
                    onClick = {
                        val next = order.toMutableList()
                        val item = next.removeAt(index)
                        next.add(index + 1, item)
                        order = next
                        config.setStringList("sources.priority", next)
                    }
                ) { Text("下移") }
            }
        }
        Row(
            horizontalArrangement = Arrangement.End,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp)
        ) {
            TextButton(onClick = {
                val next = known.toList()
                order = next
                config.setStringList("sources.priority", next)
            }) { Text("恢复默认顺序") }
        }
    }
}
